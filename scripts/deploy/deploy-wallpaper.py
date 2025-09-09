# deploy-wallpaper.py
import os
import json
import shutil
import errno
from json import JSONDecodeError
from pathlib import Path
from config_loader import OUTPUT_BASE_DIR, build_view_key, canonicalize

PROJECTS_JSON_PATH = Path("projects.json")
VIEWS_JSON_PATH = Path("views_config.json")
RUNTIME_CFG_PATH = Path("runtime_config.json")

# env overrides (optional)
ENV_STAGE_ONLY = os.environ.get("STAGE_ONLY", "")
ENV_CLEAN = os.environ.get("CLEAN_MATERIALS", "")
ENV_HOLD_LAST = os.environ.get("HOLD_LAST_FRAMES", "")
ENV_HOLD_MODE = os.environ.get("HOLD_MODE", "")

def load_runtime_cfg():
    cfg = {
        "defaults": {
            "fps": 2.0,
            "hold_last_sec": 0,
            "clean_materials": False,
            "stage_only": False,
            "hold_mode": "hardlink",  # "hardlink" | "copy"
        },
        "views": {}
    }
    if RUNTIME_CFG_PATH.exists():
        try:
            cfg.update(json.loads(RUNTIME_CFG_PATH.read_text(encoding="utf-8")))
        except Exception:
            pass
    return cfg

def effective_opts(view_key: str, runtime_cfg: dict):
    d = dict(runtime_cfg.get("defaults", {}))
    d.update(runtime_cfg.get("views", {}).get(view_key, {}))
    # env overrides
    if ENV_CLEAN:
        d["clean_materials"] = ENV_CLEAN == "1"
    if ENV_STAGE_ONLY:
        d["stage_only"] = ENV_STAGE_ONLY == "1"
    if ENV_HOLD_LAST:
        try:
            # If user gave a number, interpret as “frames”; convert to seconds using fps
            frames = int(ENV_HOLD_LAST)
            d["hold_last_sec"] = frames / float(d.get("fps", 2.0))
        except Exception:
            pass
    if ENV_HOLD_MODE:
        d["hold_mode"] = ENV_HOLD_MODE
    return d

def find_parent_dir_for_key(output_root: Path, canonical_key: str) -> Path | None:
    direct = output_root / canonical_key
    if direct.is_dir():
        return direct
    for child in output_root.iterdir():
        if child.is_dir() and canonicalize(child.name) == canonical_key:
            return child
    return None

def try_hardlink(src: Path, dst: Path) -> bool:
    try:
        if dst.exists():
            dst.unlink()
        os.link(src, dst)  # NTFS hardlink
        return True
    except OSError as e:
        # Windows returns errno for cross-device or other issues
        if e.errno in (errno.EXDEV, errno.EPERM, errno.EACCES, errno.EIO):
            return False
        # As a safe default, say False on unexpected errors too
        return False

def copy_or_link(src: Path, dst: Path, use_hardlink: bool) -> None:
    if use_hardlink:
        if try_hardlink(src, dst):
            return
    # fallback to real copy
    shutil.copy2(src, dst)

def stage_from_latest_run(parent_dir: Path, fps: float, hold_last_sec: float, hold_mode: str) -> Path | None:
    all_runs = [d for d in parent_dir.iterdir() if d.is_dir() and d.name != 'staging']
    if not all_runs:
        print(f"  [FAIL] No downloaded frame sets found in {parent_dir}")
        return None

    latest_run_folder = max(all_runs, key=lambda d: d.stat().st_mtime)
    print(f"  [1/4] Source: {latest_run_folder.name}")

    staging_dir = parent_dir / "staging"
    staging_dir.mkdir(exist_ok=True)

    # clean staging before restage
    for p in staging_dir.glob("frame_*.png"):
        try: p.unlink()
        except: pass

    source_files = sorted(latest_run_folder.glob("*.png"))
    if not source_files:
        print("  [FAIL] No .png frames in latest folder.")
        return None

    use_hardlink = (hold_mode == "hardlink")

    # rename into staging via hardlink (space-efficient)
    for i, frame_path in enumerate(source_files):
        dst = staging_dir / f"frame_{i:03d}.png"
        copy_or_link(frame_path, dst, use_hardlink)

    # compute “hold” count from seconds × fps
    hold_frames = max(0, int(round(hold_last_sec * max(0.1, float(fps)))))
    if hold_frames > 0:
        last_idx = len(source_files) - 1
        last_frame = staging_dir / f"frame_{last_idx:03d}.png"
        if last_frame.exists():
            for k in range(1, hold_frames + 1):
                dst = staging_dir / f"frame_{last_idx + k:03d}.png"
                copy_or_link(last_frame, dst, use_hardlink)
        print(f"  [SUCCESS] Staged {len(source_files)} + hold({hold_frames}) = {len(list(staging_dir.glob('frame_*.png')))} frames.")
    else:
        print(f"  [SUCCESS] Staged {len(source_files)} frames.")

    # copy manifest for provenance
    src_manifest = latest_run_folder / "manifest.json"
    if src_manifest.exists():
        shutil.copy2(src_manifest, staging_dir / "current_manifest.json")

    return staging_dir

def deploy_latest_frames(view_config: dict, project_path_str: str, opts: dict):
    project_path = Path(project_path_str)
    key = build_view_key(view_config)

    print(f"\n{'='*20}\n  Deploying '{key}'\n{'='*20}")
    parent_dir = find_parent_dir_for_key(OUTPUT_BASE_DIR, key)
    if parent_dir is None:
        print(f"  [FAIL] Source folder not found for key: {key}")
        return

    staging_dir = stage_from_latest_run(
        parent_dir,
        fps=float(opts.get("fps", 2.0)),
        hold_last_sec=float(opts.get("hold_last_sec", 0)),
        hold_mode=str(opts.get("hold_mode", "hardlink"))
    )
    if staging_dir is None:
        return

    if bool(opts.get("stage_only", False)):
        print("  [3/4] Stage-only: skipping copy to WE.")
        print("  [4/4] Done.")
        return

    materials_path = Path(project_path_str) / "materials"
    if not materials_path.is_dir():
        print(f"  [FAIL] 'materials' folder not found: {materials_path}")
        return

    # optional clean to bust caches
    if bool(opts.get("clean_materials", False)):
        for p in materials_path.glob("*.png"):
            try: p.unlink()
            except: pass

    print("  [3/4] Copying staged frames to WE materials...")
    copied = 0
    for frame in sorted(staging_dir.glob("frame_*.png")):
        shutil.copy2(str(frame), str(materials_path))
        copied += 1
    print(f"  [SUCCESS] Copied {copied} frames.")

    # manifest next to project (optional)
    try:
        m = staging_dir / "current_manifest.json"
        if m.exists():
            shutil.copy2(m, Path(project_path_str) / "current_manifest.json")
            print("  ℹ[ALERT]  current_manifest.json written.")
    except Exception as e:
        print(f"  [WARN]  manifest copy failed: {e}")

    print("  [4/4] Done.")

def main():
    runtime_cfg = load_runtime_cfg()

    try:
        views = json.loads(VIEWS_JSON_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, JSONDecodeError) as e:
        print(f"[FAIL] Problem with {VIEWS_JSON_PATH}: {e}"); return
    try:
        projs_raw = json.loads(PROJECTS_JSON_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, JSONDecodeError) as e:
        print(f"[FAIL] Problem with {PROJECTS_JSON_PATH}: {e}"); return

    projects = { canonicalize(p.get("view_name","") or p.get("view_name_base","")): p["project_path"] for p in projs_raw }

    for view in views:
        key = build_view_key(view)
        proj = projects.get(key) or projects.get(canonicalize(key))
        if proj:
            opts = effective_opts(key, runtime_cfg)
            deploy_latest_frames(view, proj, opts)
        else:
            print(f"ℹ[ALERT]  Skip '{key}' — no projects.json entry")

    print("\n[SUCCESS] All deployment tasks complete.")

if __name__ == "__main__":
    main()
