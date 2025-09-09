# set_static_wallpapers.py
# Works with either pywin32 (Dispatch) or comtypes (CreateObject).
# Skips the "live" monitor (from LIVE_MONITOR_INDEX env or runtime_config.json).

from __future__ import annotations
import json, os
from pathlib import Path
from typing import Optional, List, Tuple

# ---- Try pywin32 first; fall back to comtypes ----
HAVE_PYWIN32 = False
try:
    import win32com.client as win32
    HAVE_PYWIN32 = True
except Exception:
    pass

import ctypes
from ctypes import POINTER, byref, c_int, c_ulong, c_wchar_p, Structure, wintypes

# comtypes is only required if pywin32 is unavailable
import comtypes
from comtypes import GUID, HRESULT, IUnknown, COMMETHOD
from comtypes.client import CreateObject

# ---------------- Config ----------------
RUNTIME_CONFIG = Path("runtime_config.json")

def _load_runtime_config() -> dict:
    if RUNTIME_CONFIG.exists():
        try:
            return json.loads(RUNTIME_CONFIG.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def live_monitor_index() -> Optional[int]:
    env = os.environ.get("LIVE_MONITOR_INDEX")
    if env and env.strip().isdigit():
        return int(env.strip())
    cfg = _load_runtime_config()
    if isinstance(cfg.get("live_index"), int):
        return cfg["live_index"]
    defaults = cfg.get("defaults") or {}
    if isinstance(defaults.get("live_index"), int):
        return defaults["live_index"]
    return None

# ---------------- COM definitions (for comtypes path) ----------------
CLSID_DesktopWallpaper = GUID("{C2CF3110-460E-4FC1-B9D0-8A1C0C9CC4BD}")
IID_IDesktopWallpaper  = GUID("{B92B56A9-8B55-4E14-9A89-0199BBB6F93B}")

class RECT(Structure):
    _fields_ = [
        ("left",   wintypes.LONG),
        ("top",    wintypes.LONG),
        ("right",  wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]

DWPOS_CENTER  = 0
DWPOS_TILE    = 1
DWPOS_STRETCH = 2
DWPOS_FIT     = 3
DWPOS_FILL    = 4
DWPOS_SPAN    = 5

class IDesktopWallpaper(IUnknown):
    _iid_ = IID_IDesktopWallpaper
    _methods_ = [
        COMMETHOD([], HRESULT, 'SetWallpaper',
                  (['in'], c_wchar_p, 'monitorId'),
                  (['in'], c_wchar_p, 'wallpaper')),
        COMMETHOD([], HRESULT, 'GetWallpaper',
                  (['in'], c_wchar_p, 'monitorId'),
                  (['out'], POINTER(c_wchar_p), 'wallpaper')),
        COMMETHOD([], HRESULT, 'GetMonitorDevicePathAt',
                  (['in'], c_ulong, 'monitorIndex'),
                  (['out'], POINTER(c_wchar_p), 'monitorId')),
        COMMETHOD([], HRESULT, 'GetMonitorDevicePathCount',
                  (['out'], POINTER(c_ulong), 'count')),
        COMMETHOD([], HRESULT, 'GetMonitorRECT',
                  (['in'], c_wchar_p, 'monitorId'),
                  (['out'], POINTER(RECT), 'displayRect')),
        COMMETHOD([], HRESULT, 'SetBackgroundColor',
                  (['in'], c_ulong, 'color')),
        COMMETHOD([], HRESULT, 'GetBackgroundColor',
                  (['out'], POINTER(c_ulong), 'color')),
        COMMETHOD([], HRESULT, 'SetPosition',
                  (['in'], c_int, 'position')),
        COMMETHOD([], HRESULT, 'GetPosition',
                  (['out'], POINTER(c_int), 'position')),
    ]

def _get_dw():
    """Return a DesktopWallpaper object (pywin32 if available, else comtypes)."""
    if HAVE_PYWIN32:
        return ("pywin32", win32.Dispatch("DesktopWallpaper"))
    # comtypes path
    comtypes.CoInitialize()
    try:
        return ("comtypes", CreateObject(CLSID_DesktopWallpaper, interface=IDesktopWallpaper))
    except Exception:
        comtypes.CoUninitialize()
        raise

# ------------- Backend-agnostic helpers -------------
def _count_monitors(dw):
    """pywin32 returns int; comtypes needs byref."""
    try:
        # comtypes path (method expects OUT param)
        cnt = c_ulong(0)
        dw.GetMonitorDevicePathCount(byref(cnt))
        return cnt.value
    except TypeError:
        # pywin32 path (returns int directly)
        return int(dw.GetMonitorDevicePathCount())

def _monitor_path_at(dw, idx: int) -> str:
    try:
        # comtypes OUT param
        mid = c_wchar_p()
        dw.GetMonitorDevicePathAt(idx, byref(mid))
        return mid.value
    except TypeError:
        # pywin32 direct return
        return dw.GetMonitorDevicePathAt(idx)

def _set_wallpaper(dw, monitor_id: str, image_path: str):
    # Signature is the same for both: (monitorId, path)
    dw.SetWallpaper(monitor_id, image_path)

# ---------------- Public API ----------------
def set_wallpapers_for_monitors(paths: List[Path], scale_mode: int = DWPOS_FILL) -> None:
    """
    Apply wallpapers across all monitors, skipping the 'live' monitor (index from env/config).
    """
    if not paths:
        print("[INFO] No image paths provided; skipping wallpaper set.")
        return

    backend, dw = _get_dw()
    try:
        # Global position
        try:
            dw.SetPosition(scale_mode)
        except Exception as e:
            print(f"[WARN] SetPosition failed ({e}); continuing.")

        mcount = _count_monitors(dw)
        live_idx = live_monitor_index()

        ids: List[Tuple[int, str]] = []
        for i in range(mcount):
            if live_idx is not None and i == live_idx:
                continue
            ids.append((i, _monitor_path_at(dw, i)))

        imgs = [str(Path(p).resolve()) for p in paths]
        n = len(imgs)
        for i, mon_id in ids:
            _set_wallpaper(dw, mon_id, imgs[i % n])

        print(f"[OK] Applied {len(ids)} wallpapers using {backend} (skipped live index {live_idx}).")

    finally:
        if backend == "comtypes":
            try:
                comtypes.CoUninitialize()
            except Exception:
                pass

def time_band_now() -> str:
    from datetime import datetime
    h = datetime.now().hour
    if 5 <= h < 12:
        return "morning"
    if 12 <= h < 17:
        return "afternoon"
    return "evening"

if __name__ == "__main__":
    import sys
    imgs = [Path(p) for p in sys.argv[1:]]
    set_wallpapers_for_monitors(imgs)
