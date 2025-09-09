# list_monitors.py
# Enumerate monitors + current wallpaper via IDesktopWallpaper (Windows 8+)
# Requires: pip install comtypes

import sys
import ctypes
from ctypes import POINTER, c_ulong, c_wchar_p
import comtypes
from comtypes import GUID, HRESULT, IUnknown, COMMETHOD
from comtypes.client import CreateObject

class RECT(ctypes.Structure):
    _fields_ = [
        ("left",   ctypes.c_long),
        ("top",    ctypes.c_long),
        ("right",  ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]

class IDesktopWallpaper(IUnknown):
    _iid_ = GUID("{B92B56A9-8B55-4E14-9A89-0199BBB6F93B}")
    _methods_ = [
        COMMETHOD([], HRESULT, 'SetWallpaper',
                  (['in'], c_wchar_p, 'monitorId'),
                  (['in'], c_wchar_p, 'wallpaper')),

        COMMETHOD([], HRESULT, 'GetWallpaper',
                  (['in'], c_wchar_p, 'monitorId'),
                  (['out', 'retval'], POINTER(c_wchar_p), 'wallpaper')),

        COMMETHOD([], HRESULT, 'GetMonitorDevicePathAt',
                  (['in'], c_ulong, 'monitorIndex'),
                  (['out', 'retval'], POINTER(c_wchar_p), 'monitorId')),

        COMMETHOD([], HRESULT, 'GetMonitorDevicePathCount',
                  (['out', 'retval'], POINTER(c_ulong), 'count')),

        COMMETHOD([], HRESULT, 'GetMonitorRECT',
                  (['in'], c_wchar_p, 'monitorId'),
                  (['out', 'retval'], POINTER(RECT), 'displayRect')),
    ]

CLSID_DesktopWallpaper = GUID("{C2CF3110-460E-4FC1-B9D0-8A1C0C9CC4BD}")

def main():
    print("Initializing COM…")
    try:
        comtypes.CoInitialize()
        print("Creating DesktopWallpaper COM object…")
        dw = CreateObject(CLSID_DesktopWallpaper, interface=IDesktopWallpaper)

        n = dw.GetMonitorDevicePathCount()
        print(f"\nFound {n} monitor(s).\n")

        for i in range(n):
            monitor_id = dw.GetMonitorDevicePathAt(i)
            rc = dw.GetMonitorRECT(monitor_id)

            # GetWallpaper returns a string directly
            wallpaper = dw.GetWallpaper(monitor_id) or ""

            print(f"Index {i}:")
            print(f"  monitorId : {monitor_id}")
            print(f"  RECT      : (left={rc.left}, top={rc.top}, right={rc.right}, bottom={rc.bottom})")
            print(f"  wallpaper : {wallpaper or '(none / slideshow)'}\n")

        print("Use the Index (0-based) as LIVE_MONITOR_INDEX.")
    except Exception as e:
        print("[FAIL] Error:", e)
        sys.exit(1)
    finally:
        comtypes.CoUninitialize()

if __name__ == "__main__":
    main()