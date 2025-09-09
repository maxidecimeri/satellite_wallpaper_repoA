# regen_places_from_filenames.py
# Extract place candidates from image filenames and geocode offline-first.
# Outputs places_seed_geocoded.csv with multi-level candidates + final match.

import argparse, csv, json, re, time, unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlencode
import urllib.request, urllib.error

OUTPUT_CSV = Path("places_seed_geocoded.csv")
CUSTOM_PLACES_CSV = Path("places_custom.csv")
CACHE_PATH = Path("geocode_cache.json")
VALID_EXTS = {".jpg", ".jpeg", ".png"}

NON_PLACE_TOKENS = {
    "the","and","of","in","on","at","by","a","an","to","from","between","over","under","with",
    "near","along","above","below","into","out","onto","off","for",
    "sunrise","sunset","dawn","dusk","morning","afternoon","evening","night",
    "aerial","view","landscape","scenic","panorama","panoramic","hdr",
    "wallpaper","desktop","background","image","photo",
    "horiz","vert","wide","ultrawide","4k","8k","uhd",
}

# --- Gazetteer (extend freely) ---
BASE_GAZETTEER: Dict[str, Tuple[float, float, str, str]] = {
    # Countries
    "iceland": (64.9631, -19.0208, "EU", "country"),
    "thailand": (15.8700, 100.9925, "AS", "country"),
    "norway": (60.4720, 8.4689, "EU", "country"),
    "vietnam": (14.0583, 108.2772, "AS", "country"),
    "japan": (36.2048, 138.2529, "AS", "country"),
    "united states": (39.8283, -98.5795, "NA", "country"),
    "usa": (39.8283, -98.5795, "NA", "country"),
    "france": (46.2276, 2.2137, "EU", "country"),
    "italy": (41.8719, 12.5674, "EU", "country"),
    "spain": (40.4637, -3.7492, "EU", "country"),
    "portugal": (39.3999, -8.2245, "EU", "country"),
    "greece": (39.0742, 21.8243, "EU", "country"),
    "australia": (-25.2744, 133.7751, "OC", "country"),
    "new zealand": (-40.9006, 174.8860, "OC", "country"),

    # Cities
    "pattaya": (12.9236, 100.8825, "AS", "city"),
    "bangkok": (13.7563, 100.5018, "AS", "city"),
    "tokyo": (35.6762, 139.6503, "AS", "city"),
    "paris": (48.8566, 2.3522, "EU", "city"),
    "london": (51.5074, -0.1278, "EU", "city"),
    "rome": (41.9028, 12.4964, "EU", "city"),
    "barcelona": (41.3851, 2.1734, "EU", "city"),
    "amsterdam": (52.3676, 4.9041, "EU", "city"),
    "athens": (37.9838, 23.7275, "EU", "city"),
    "sydney": (-33.8688, 151.2093, "OC", "city"),
    "san francisco": (37.7749, -122.4194, "NA", "city"),
    "new york": (40.7128, -74.0060, "NA", "city"),
    "chicago": (41.8781, -87.6298, "NA", "city"),

    # US states (centroids)
    "alaska": (64.2008, -149.4937, "NA", "state"),
    "hawaii": (20.7984, -156.3319, "NA", "state"),
    "arizona": (34.0489,-111.0937, "NA","state"),
    "california": (36.7783,-119.4179, "NA","state"),
    "oregon": (43.8041,-120.5542, "NA","state"),
    "washington": (47.7511,-120.7401, "NA","state"),
    "texas": (31.0,-100.0, "NA","state"),
    "florida": (27.6648,-81.5158, "NA","state"),
    "new york state": (42.9134,-75.5963, "NA","state"),
    "colorado": (39.5501,-105.7821, "NA","state"),
    "utah": (39.3210,-111.0937, "NA","state"),
    "nevada": (38.8026,-116.4194, "NA","state"),
    "michigan": (44.3148,-85.6024, "NA","state"),
    "illinois": (40.6331,-89.3985, "NA","state"),
    "new hampshire": (43.1939, -71.5724, "NA","state"),

    # Landmarks / regions
    "lofoten islands": (68.2090, 13.8456, "EU", "landmark"),
    "jokulsarlon": (64.0482, -16.1790, "EU", "landmark"),
    "jökulsárlón": (64.0482, -16.1790, "EU", "landmark"),
    "big sur": (36.3615, -121.8563, "NA", "landmark"),
    "yosemite": (37.8651, -119.5383, "NA", "landmark"),
    "amalfi coast": (40.6333, 14.6029, "EU", "landmark"),
    "cinque terre": (44.1460, 9.6550, "EU", "landmark"),
}

LEVEL_PRIORITY = {"landmark": 3, "city": 2, "state": 1, "country": 0}
SEP_RE = re.compile(r"[-_.,]+")

def strip_accents(s: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))

def canonical(s: str) -> str:
    s = strip_accents(s)
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s

def tokens_from_basename(name: str) -> List[str]:
    stem = Path(name).stem
    parts = [p for p in SEP_RE.split(stem) if p]
    parts = [re.sub(r"\d{3,4}x\d{3,4}", "", p) for p in parts]
    return [p for p in parts if p and not p.isdigit()]

def level_of(key: str) -> str:
    return BASE_GAZETTEER.get(key, (None,None,"",""))[3] if key in BASE_GAZETTEER else ""

def best_match_among(cands: List[str], gaz: Dict[str, Tuple[float,float,str,str]]) -> Optional[Tuple[str,float,float,str,str]]:
    # prefer landmark > city > state > country; break ties by length (more specific phrases)
    ranked = []
    for c in cands:
        if c in gaz:
            lat, lon, region, level = gaz[c]
            ranked.append((LEVEL_PRIORITY.get(level, -1), len(c), c, lat, lon, region, level))
    if not ranked:
        return None
    ranked.sort(reverse=True)  # highest priority, then longer text
    _,_, key, lat, lon, region, level = ranked[0]
    return (key, lat, lon, region, level)

def extract_candidates(file_basename: str) -> Dict[str, str]:
    # Return first good candidate per level found in the name
    words = tokens_from_basename(file_basename)
    words = [w for w in words if canonical(w) not in NON_PLACE_TOKENS]

    # Build n-grams up to 3 tokens, canonicalize, and look up against gazetteer
    seen = set()
    cand = {"landmark":"", "city":"", "state":"", "country":""}
    for n in (3,2,1):
        for i in range(len(words)-n+1):
            phrase = " ".join(words[i:i+n])
            key = canonical(phrase)
            if key in seen: 
                continue
            seen.add(key)
            if key in BASE_GAZETTEER:
                lvl = level_of(key)
                if lvl and not cand[lvl]:
                    cand[lvl] = phrase  # store the original phrase form
    return cand

# --- Optional online fallback ---
def fetch_url(url: str, headers: dict, timeout: int = 15) -> Optional[dict]:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            return json.loads(data.decode("utf-8", errors="ignore"))
    except Exception:
        return None

def geocode_nominatim(q: str, sleep: float = 1.0) -> Optional[Tuple[float, float, str]]:
    time.sleep(sleep)
    base = "https://nominatim.openstreetmap.org/search"
    url = f"{base}?{urlencode({'q': q, 'format': 'json', 'limit': 1})}"
    j = fetch_url(url, {"User-Agent": "satellite-wallpaper/1.0"})
    if isinstance(j, list) and j:
        try:
            return (float(j[0]["lat"]), float(j[0]["lon"]), "")
        except Exception:
            return None
    return None

def load_custom() -> Dict[str, Tuple[float,float,str,str]]:
    out = {}
    if CUSTOM_PLACES_CSV.exists():
        with CUSTOM_PLACES_CSV.open("r", encoding="utf-8") as f:
            rdr = csv.DictReader(f)
            for r in rdr:
                try:
                    out[canonical(r["name"])] = (float(r["lat"]), float(r["lon"]), r.get("region",""), r.get("level","city"))
                except Exception:
                    pass
    return out

def band_from_parent(path: Path) -> Optional[str]:
    parts = [p.name.lower() for p in path.parents]
    for b in ("morning","afternoon","evening","space"):
        if b in parts: return b
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="static_backgrounds", help="Root folder to scan")
    ap.add_argument("--band-from-parent", action="store_true")
    ap.add_argument("--use-nominatim", action="store_true")
    ap.add_argument("--sleep", type=float, default=1.0)
    ap.add_argument("--max-api", type=int, default=50)
    args = ap.parse_args()

    root = Path(args.root)
    files = [p for p in root.rglob("*") if p.suffix.lower() in VALID_EXTS]

    custom = load_custom()
    gaz = {**BASE_GAZETTEER, **custom}
    rows, api_used = [], 0

    for img in files:
        rel_path = str(img.relative_to(root))
        basename = img.name
        band = band_from_parent(img) if args.band_from_parent else ""

        cands = extract_candidates(basename)  # strings (original form)
        # Build canonical list in priority order for matching
        ordered_keys = []
        for lvl in ("landmark","city","state","country"):
            if cands[lvl]:
                ordered_keys.append(canonical(cands[lvl]))

        match = best_match_among(ordered_keys, gaz)

        if not match and args.use_nominatim and ordered_keys and api_used < args.max_api:
            api_used += 1
            q = cands["landmark"] or cands["city"] or cands["state"] or cands["country"]
            res = geocode_nominatim(q, sleep=args.sleep)
            if res:
                la, lo, reg = res
                rows.append({
                    "rel_path": rel_path,
                    "file_basename": basename,
                    "time_band": band,
                    "cand_landmark": cands["landmark"],
                    "cand_city": cands["city"],
                    "cand_state": cands["state"],
                    "cand_country": cands["country"],
                    "matched": q,
                    "match_level": "",
                    "lat": la, "lon": lo, "region": reg,
                    "source": "nominatim", "confidence": "med",
                })
                continue

        if match:
            key, la, lo, reg, lvl = match
            rows.append({
                "rel_path": rel_path,
                "file_basename": basename,
                "time_band": band,
                "cand_landmark": cands["landmark"],
                "cand_city": cands["city"],
                "cand_state": cands["state"],
                "cand_country": cands["country"],
                "matched": key, "match_level": lvl,
                "lat": la, "lon": lo, "region": reg,
                "source": "gazetteer" if canonical(key) not in custom else "custom",
                "confidence": "high" if lvl in ("landmark","city") else "med",
            })
        else:
            rows.append({
                "rel_path": rel_path,
                "file_basename": basename,
                "time_band": band,
                "cand_landmark": cands["landmark"],
                "cand_city": cands["city"],
                "cand_state": cands["state"],
                "cand_country": cands["country"],
                "matched": "", "match_level": "",
                "lat": "", "lon": "", "region": "",
                "source": "", "confidence": "",
            })

    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "rel_path","file_basename","time_band",
            "cand_landmark","cand_city","cand_state","cand_country",
            "matched","match_level","lat","lon","region","source","confidence"
        ])
        w.writeheader()
        w.writerows(rows)

    print(f"✅ Wrote {OUTPUT_CSV} with {len(rows)} rows. Nominatim calls used: {api_used}.")
if __name__ == "__main__":
    main()
