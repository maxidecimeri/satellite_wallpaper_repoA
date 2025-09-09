"""
Pick 2 time-of-day-matched static images and apply them to non-live monitors.
For MVP we do NOT filter by geographic bbox yet — just time-band.

Later, we’ll read each image’s EXIF/sidecar (lat/lon) and intersect
with the sat view’s bbox to choose more relevant companions.
"""

from __future__ import annotations
import json
import random
from pathlib import Path
from typing import List

# Import STATIC_DIR from a configuration file, assuming its existence
try:
    from config_loader import STATIC_DIR
except ImportError:
    # Fallback if config_loader.py is not available
    STATIC_DIR = "static_images"

from set_static_wallpapers import set_wallpapers_for_monitors, time_band_now

PROJECTS_JSON = Path("projects.json")
VALID_EXTS = {".jpg", ".jpeg", ".png"}

def _list_images_under(root: Path, limit_band: str | None) -> List[Path]:
    """
    Lists image files under a given root directory, optionally filtering by time band.
    """
    if limit_band:
        band_dir = root / "manual_labels" / limit_band
        if band_dir.is_dir():
            imgs = [p for p in band_dir.rglob("*") if p.suffix.lower() in VALID_EXTS]
            if imgs:
                return imgs
    
    # Fallback to all images under the root directory if no band is specified
    # or if the band-specific directory is empty or doesn't exist
    return [p for p in root.rglob("*") if p.suffix.lower() in VALID_EXTS]

def main():
    """
    Main function to select and set companion wallpapers.
    """
    # Attempt to load project configuration (optional for future features)
    try:
        if PROJECTS_JSON.exists():
            projects = json.loads(PROJECTS_JSON.read_text(encoding="utf-8"))
            if isinstance(projects, list) and projects:
                # view_name is not used in this version but is kept for future expansion
                view_name = projects[0].get("view_name_base")
            else:
                view_name = None
        else:
            view_name = None
    except Exception as e:
        print(f"Warning: Could not load projects.json. {e}")
        view_name = None

    band = time_band_now()
    pool = _list_images_under(Path(STATIC_DIR), band)
    
    if not pool:
        print("No static images found; nothing to do.")
        return

    random.shuffle(pool)
    # Choose two unique images from the pool
    chosen_paths = random.sample(pool, min(2, len(pool)))
    
    print(f"Time band: {band} | Chosen: {', '.join(str(p) for p in chosen_paths)}")

    # Call the wallpaper setter, which handles skipping the live monitor
    set_wallpapers_for_monitors(chosen_paths)

if __name__ == "__main__":
    main()