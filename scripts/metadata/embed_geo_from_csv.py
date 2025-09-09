# embed_geo_from_csv.py
# Adds:
#  - --levels filter (unchanged)
#  - robust filename parsing that strips appended time-of-day descriptors
#  - optional inference of time_band from that descriptor
#  - avoids double-joining root if CSV already includes it
import argparse
import csv
import json
import re
from pathlib import Path
from typing import Tuple, Optional
from PIL import Image
import piexif

# ---------------- EXIF helpers ----------------
def to_rational(num: float) -> Tuple[int, int]:
    from fractions import Fraction
    f = Fraction(num).limit_denominator(1_000_000)
    return (f.numerator, f.denominator)

def deg_to_dms_rationals(deg: float):
    ref = "N" if deg >= 0 else "S"
    if deg < 0: deg = -deg
    d = int(deg); m_float = (deg - d) * 60; m = int(m_float); s = (m_float - m) * 60
    return ref, (to_rational(d), to_rational(m), to_rational(s))

def lon_to_dms_rationals(lon: float):
    ref = "E" if lon >= 0 else "W"
    if lon < 0: lon = -lon
    d = int(lon); m_float = (lon - d) * 60; m = int(m_float); s = (m_float - m) * 60
    return ref, (to_rational(d), to_rational(m), to_rational(s))

def write_exif_gps(jpeg_path: Path, lat: float, lon: float, place: Optional[str] = None, backup: bool = False) -> bool:
    try:
        if backup:
            bak = jpeg_path.with_suffix(jpeg_path.suffix + ".bak")
            if not bak.exists():
                bak.write_bytes(jpeg_path.read_bytes())
        img = Image.open(jpeg_path)
        try:
            exif_bytes = img.info.get("exif", b"")
            exif_dict = piexif.load(exif_bytes) if exif_bytes else {"0th":{}, "Exif":{}, "GPS":{}, "1st":{}, "thumbnail": None}
        except Exception:
            exif_dict = {"0th":{}, "Exif":{}, "GPS":{}, "1st":{}, "thumbnail": None}
        lat_ref, lat_dms = deg_to_dms_rationals(lat)
        lon_ref, lon_dms = lon_to_dms_rationals(lon)
        gps_ifd = exif_dict.get("GPS", {})
        gps_ifd[piexif.GPSIFD.GPSLatitudeRef]  = lat_ref.encode("ascii")
        gps_ifd[piexif.GPSIFD.GPSLatitude]     = lat_dms
        gps_ifd[piexif.GPSIFD.GPSLongitudeRef] = lon_ref.encode("ascii")
        gps_ifd[piexif.GPSIFD.GPSLongitude]    = lon_dms
        exif_dict["GPS"] = gps_ifd
        if place:
            exif_dict["0th"][piexif.ImageIFD.XPTitle] = place.encode("utf-16le") + b"\x00\x00"
        exif_new = piexif.dump(exif_dict)
        img.save(jpeg_path, "jpeg", exif=exif_new, quality=95)
        return True
    except Exception as e:
        print(f"  ❌ EXIF write failed for {jpeg_path}: {e}")
        return False

# ---------------- CSV / path helpers ----------------
FILENAME_CANDIDATES = ["rel_path","filename","file","path","relpath","relative_path","image","img"]

# match: everything up to a valid image extension, then optional trailing descriptor
FILE_AND_BAND_RE = re.compile(
    r"""^\s*
        (?P<path>.+?\.(?:jpe?g|png|webp))        # capture real file path
        (?:\s*                                   # optional separator + band
           (?:\||-|—|–|\)|\]|\:)?
           \s*
           [\(\[\{]?
           \s*(?P<band>morning|afternoon|evening|night|dawn|dusk|day|sunset|sunrise|blue\s*hour|golden\s*hour)\s*
           [\)\]\}]?
        )?
        \s*$""",
    re.IGNORECASE | re.VERBOSE
)

TIME_BAND_NORMALIZE = {
    "morning":"morning",
    "afternoon":"afternoon",
    "evening":"evening",
    "night":"evening",     # map "night" to evening bucket unless you want a separate bucket
    "dawn":"morning",
    "dusk":"evening",
    "day":"afternoon",
    "sunset":"evening",
    "sunrise":"morning",
    "blue hour":"evening",
    "golden hour":"evening",
}

def pick_filename_key(fieldnames):
    if not fieldnames: return None
    lower = {f.lower(): f for f in fieldnames}
    for k in FILENAME_CANDIDATES:
        if k in lower: return lower[k]
    return None

def split_path_and_band(raw: str) -> tuple[str, Optional[str]]:
    s = (raw or "").strip().replace("\\","/")
    m = FILE_AND_BAND_RE.match(s)
    if not m:
        # if we can't match, fall back to trimming after first known extension
        for ext in (".jpg",".jpeg",".png",".webp"):
            idx = s.lower().find(ext)
            if idx != -1:
                return s[:idx+len(ext)], None
        return s, None
    path = m.group("path")
    band = m.group("band")
    if band:
        band = TIME_BAND_NORMALIZE.get(band.lower().replace("  "," ").strip(), band)
    return path, band

def join_under_root(root: Path, rel: str) -> Path:
    # Avoid double-joining if rel already starts with the root folder name
    rel_path = Path(rel)
    if rel_path.is_absolute():
        return rel_path
    # If the CSV already includes the root prefix, don't add it again
    try:
        if str(rel_path).split("/")[0] == root.name:
            return Path(rel)
    except Exception:
        pass
    return root / rel

# ---------------- Main ----------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--root", default="static_backgrounds")
    ap.add_argument("--write-exif", action="store_true")
    ap.add_argument("--write-sidecars", action="store_true")
    ap.add_argument("--backup", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--levels",
        default="landmark,city,state",
        help="Comma-separated match levels allowed for EXIF (e.g., 'city,state')."
    )
    args = ap.parse_args()

    allowed_levels = {s.strip().lower() for s in args.levels.split(",") if s.strip()}

    root = Path(args.root)

    with open(args.csv, "r", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        fname_key = pick_filename_key(rdr.fieldnames)
        if not fname_key:
            raise SystemExit(f"❌ No filename column found. Headers: {rdr.fieldnames}")

        rows = list(rdr)

    exif_ok = sidecars = skipped = 0
    missing_files = blank_filenames = dir_hits = 0

    for r in rows:
        raw_name = r.get(fname_key) or ""
        if not raw_name.strip():
            blank_filenames += 1
            continue

        rel_clean, inferred_band = split_path_and_band(raw_name)
        img_path = join_under_root(root, rel_clean)

        lat_s = (r.get("lat") or "").strip()
        lon_s = (r.get("lon") or "").strip()
        place = (r.get("matched") or r.get("inferred_place") or "").strip()
        region = (r.get("region") or "").strip()
        time_band = (r.get("time_band") or "").strip() or (inferred_band or "")
        level = (r.get("match_level") or "").strip().lower()

        if not img_path.exists():
            print(f"⚠️ Missing file: {img_path}")
            missing_files += 1
            continue
        if img_path.is_dir():
            print(f"• Path is a directory, skipped: {img_path}")
            dir_hits += 1
            continue

        payload = {
            "place": place,
            "lat": float(lat_s) if lat_s else None,
            "lon": float(lon_s) if lon_s else None,
            "region": region,
            "time_band": time_band,
            "match_level": level,
            "source": r.get("source",""),
            "confidence": r.get("confidence",""),
        }

        ext = img_path.suffix.lower()
        if ext in (".jpg",".jpeg"):
            if args.write_exif:
                if not lat_s or not lon_s:
                    print(f"• No lat/lon for {img_path.name} — EXIF skipped")
                elif not level:
                    print(f"• No match_level for {img_path.name} — EXIF skipped")
                elif level not in allowed_levels:
                    print(f"• Level '{level}' not allowed for EXIF on {img_path.name} — skipped (allowed: {sorted(allowed_levels)})")
                else:
                    print(f"→ EXIF GPS {img_path.name}: ({lat_s},{lon_s}) [{place}] level={level} band={time_band or '-'}")
                    if not args.dry_run:
                        if write_exif_gps(img_path, float(lat_s), float(lon_s), place or None, backup=args.backup):
                            exif_ok += 1
                    else:
                        exif_ok += 1
            if args.write_sidecars:
                print(f"→ Sidecar {img_path.name}")
                if not args.dry_run:
                    sidecar = img_path.with_suffix(img_path.suffix + ".json")
                    sidecar.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                sidecars += 1
        elif ext in (".png", ".webp"):
            if args.write_sidecars:
                print(f"→ Sidecar {img_path.name}")
                if not args.dry_run:
                    sidecar = img_path.with_suffix(img_path.suffix + ".json")
                    sidecar.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                sidecars += 1
        else:
            print(f"• Unsupported extension, skipped: {img_path.name}")
            skipped += 1

    print("\n✅ Done.")
    print(f"   EXIF writes:   {exif_ok}")
    print(f"   Sidecars:      {sidecars}")
    print(f"   Skipped (ext): {skipped}")
    print(f"   Missing files: {missing_files}")
    print(f"   Blank filenames in CSV: {blank_filenames}")
    print(f"   Directory hits: {dir_hits}")

if __name__ == "__main__":
    main()
