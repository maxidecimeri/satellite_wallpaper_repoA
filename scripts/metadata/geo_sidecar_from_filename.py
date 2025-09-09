import csv
import json
import argparse
import difflib
import re
from pathlib import Path
from typing import Optional, Tuple

# CONFIG
STATIC_ROOT = Path("static_backgrounds")  # your images root
PLACES_CSV = Path("places.csv")          # local gazetteer

# Simple tokens to ignore when extracting place names from filenames
IGNORE_TOKENS = {
    "morning","afternoon","evening","night","sunrise","sunset","dawn","dusk",
    "aerial","view","landscape","scenic","panorama","panoramic","hdr","wallpaper",
    "4k","8k","uhd","wide","ultrawide","desktop","background"
}

# --- EXIF writer for JPEGs (optional) ---
def write_gps_exif_jpeg(jpeg_path: Path, lat: float, lon: float) -> bool:
    try:
        import piexif
        from PIL import Image

        def _deg_to_dms_rational(deg):
            deg_abs = abs(deg)
            d = int(deg_abs)
            m = int((deg_abs - d) * 60)
            s = round((deg_abs - d - m/60) * 3600 * 10000)
            return ((d,1),(m,1),(s,10000))

        gps_ifd = {
            piexif.GPSIFD.GPSLatitudeRef: b'N' if lat >= 0 else b'S',
            piexif.GPSIFD.GPSLatitude: _deg_to_dms_rational(lat),
            piexif.GPSIFD.GPSLongitudeRef: b'E' if lon >= 0 else b'W',
            piexif.GPSIFD.GPSLongitude: _deg_to_dms_rational(lon),
        }

        img = Image.open(jpeg_path)
        exif = img.info.get("exif", None)
        exif_dict = piexif.load(exif) if exif else {"0th":{}, "Exif":{}, "GPS":{}, "1st":{}, "thumbnail":None}
        exif_dict["GPS"] = gps_ifd
        exif_bytes = piexif.dump(exif_dict)
        img.save(jpeg_path, exif=exif_bytes)
        return True
    except Exception as e:
        print(f"[EXIF] Failed for {jpeg_path.name}: {e}")
        return False

# --- filename parsing ---
SEP_RE = re.compile(r"[-_.,]+")
PAREN_RE = re.compile(r"\(([^)]+)\)")

def normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()

def extract_place_candidate(name: str) -> Optional[str]:
    """Heuristics: prefer (Parentheses), else first chunk before separators; drop common tokens."""
    stem = Path(name).stem
    m = PAREN_RE.search(stem)
    cand = m.group(1) if m else stem
    parts = SEP_RE.split(cand)
    parts = [p for p in parts if p]  # rm empty
    # remove numeric-only parts and junk tokens
    parts = [p for p in parts if not p.isdigit()]
    parts = [p for p in parts if normalize(p) not in IGNORE_TOKENS]
    if not parts:
        return None
    # join 1–3 tokens max to avoid overlong strings
    joined = " ".join(parts[:3])
    # strip residual resolution markers like 1920x1080
    joined = re.sub(r"\d{3,4}x\d{3,4}", "", joined).strip()
    return joined or None

# --- gazetteer ---
def load_places(csv_path: Path):
    table = []
    if not csv_path.exists():
        print(f"[WARN] places.csv not found at {csv_path}. Create it with name,lat,lon[,region].")
        return table
    with csv_path.open("r", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        for r in rdr:
            try:
                table.append({
                    "name": r["name"],
                    "lat": float(r["lat"]),
                    "lon": float(r["lon"]),
                    "region": r.get("region","")
                })
            except Exception:
                pass
    return table

def lookup_place(name: str, places) -> Optional[dict]:
    if not places:
        return None
    names = [p["name"] for p in places]
    # fuzzy match
    hits = difflib.get_close_matches(name, names, n=1, cutoff=0.6)
    if not hits:
        # try title-case exact
        for p in places:
            if normalize(p["name"]) == normalize(name):
                return p
        return None
    best = hits[0]
    for p in places:
        if p["name"] == best:
            return p
    return None

def time_band_from_folder(path: Path) -> Optional[str]:
    # infer band from parent folders: /morning/, /afternoon/, /evening/, /space/
    parts = [p.name.lower() for p in path.parents]
    for band in ("morning","afternoon","evening","space"):
        if band in parts:
            return band
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-exif", action="store_true", help="Embed GPS EXIF into JPEGs (PNG will use sidecar only).")
    ap.add_argument("--dry-run", action="store_true", help="Parse/resolve only; do not write sidecars/EXIF.")
    args = ap.parse_args()

    places = load_places(PLACES_CSV)

    images = [p for p in STATIC_ROOT.rglob("*") if p.suffix.lower() in {".jpg",".jpeg",".png"}]
    if not images:
        print(f"[INFO] No images under {STATIC_ROOT}")
        return

    made = 0
    for img in images:
        cand = extract_place_candidate(img.name)
        band = time_band_from_folder(img)
        meta = {"inferred_place": cand or "", "time_band": band or ""}

        match = lookup_place(cand, places) if cand else None
        if match:
            meta.update({"place_name": match["name"], "lat": match["lat"], "lon": match["lon"], "region": match.get("region","")})
        else:
            meta.update({"place_name": "", "lat": None, "lon": None, "region": ""})

        sidecar = img.with_suffix(img.suffix + ".json")
        print(f"[META] {img.name} → {meta}")

        if not args.dry_run:
            # write sidecar json
            try:
                sidecar.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception as e:
                print(f"[WARN] sidecar write failed for {img.name}: {e}")

            # optional EXIF embed for JPEGs only
            if args.write_exif and (img.suffix.lower() in {".jpg",".jpeg"}) and match and match["lat"] is not None:
                write_gps_exif_jpeg(img, match["lat"], match["lon"])

            made += 1

    print(f"\n✅ Processed {len(images)} images. Sidecars {'created' if not args.dry_run else 'simulated'} for {made}.")

if __name__ == "__main__":
    main()
