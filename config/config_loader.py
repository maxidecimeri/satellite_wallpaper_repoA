import json
import re
from pathlib import Path

# ---------- Canonicalization (single source of truth) ----------
def canonicalize(text: str) -> str:
    """
    Normalize a string into a stable, filesystem- and key-safe form.
    - Replace micro sign(s) with ASCII 'm'
    - Replace spaces with underscores
    - Remove any char not [A-Za-z0-9_-] (note: \w is unicode-safe)
    """
    # normalize common micro variants
    text = text.replace("µ", "m").replace("μ", "m")
    # add more mappings here if needed (e.g., degree '°' → '')
    text = text.replace(" ", "_")
    return re.sub(r'[^\w\-_]', '', text)

def build_view_key(view: dict) -> str:
    """Create the canonical key 'sat_sec_im' for a view dict."""
    return canonicalize(f"{view['sat']}_{view['sec']}_{view['im']}")

# ---------- Config load ----------
_ROOT = Path(__file__).parent
_ENV_PATH = _ROOT / "config_local.json"

# Load local config (user-specific) or fall back to repo-relative defaults
if _ENV_PATH.exists():
    with open(_ENV_PATH, "r", encoding="utf-8") as f:
        _cfg = json.load(f)
else:
    _cfg = {
        "output_base_dir": str(_ROOT / "output"),
        "static_dir": str(_ROOT / "static_backgrounds"),
        "logs_dir": str(_ROOT / "logs"),
        "wallpaper_engine_path": r"C:\Program Files (x86)\Steam\steamapps\common\wallpaper_engine\wallpaper64.exe",
        "steam_protocol": "steam://rungameid/431960",
        "deploy_script_name": "deploy-wallpaper.py",
        "homepage_url": "https://rammb2.cira.colostate.edu/"
    }

# ---------- Exports ----------
OUTPUT_BASE_DIR = Path(_cfg["output_base_dir"])
STATIC_DIR = Path(_cfg["static_dir"])
LOGS_DIR = Path(_cfg["logs_dir"])
WALLPAPER_ENGINE_EXE = _cfg["wallpaper_engine_path"]
STEAM_PROTOCOL = _cfg["steam_protocol"]
DEPLOY_SCRIPT_NAME = _cfg["deploy_script_name"]
HOMEPAGE_URL = _cfg["homepage_url"]

# Ensure key dirs exist (non-fatal)
for _p in (OUTPUT_BASE_DIR, STATIC_DIR, LOGS_DIR):
    try:
        Path(_p).mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
