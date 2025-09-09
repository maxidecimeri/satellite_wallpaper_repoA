import asyncio
import shutil
import json
import re
from pathlib import Path
from playwright.async_api import async_playwright
from config_loader import OUTPUT_BASE_DIR, HOMEPAGE_URL, build_view_key
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


VIEWS_JSON_PATH = Path("views_config.json")

async def select_dropdown_option(page, button_id, option_text):
    print(f"[INFO] Selecting '{option_text}' from {button_id}")
    button = page.locator(f"#{button_id}")
    await button.wait_for(state="visible", timeout=60_000)
    await button.click()
    ul = page.locator(f'ul[aria-labelledby="{button_id}"]')
    await ul.wait_for(state="visible", timeout=15_000)
    option = ul.locator("li").filter(has_text=option_text)
    await option.wait_for(state="visible", timeout=15_000)
    await option.click()
    await ul.wait_for(state="hidden", timeout=10_000)

async def perform_download_with_timestamp(page, base_output_dir: Path):
    print("[INFO] Opening download menu...")
    await page.click("#downloadLoop")
    await asyncio.sleep(2)

    print("[INFO] Selecting 'All Images Separately'...")
    label = page.locator('label[for="allImagesSeparately"]')
    if await label.is_visible():
        await label.click()
    await asyncio.sleep(1)

    print("[INFO] Clicking 'Start Download' (preps files)...")
    await page.click("#submitDownloadOptions")

    print("[INFO] Waiting for 'Zip All Images' button...")
    zip_btn = page.locator("#downloadAllButton")
    await zip_btn.wait_for(state="visible", timeout=180_000)

    print("[INFO] Clicking 'Zip All Images' and awaiting download...")
    async with page.expect_download(timeout=180_000) as download_info:
        await zip_btn.click()
    download = await download_info.value

    zip_filename = download.suggested_filename
    match = re.search(r'(\d{14})-', zip_filename)
    if match:
        dt_str = match.group(1)
        timestamp = f"{dt_str[0:4]}-{dt_str[4:6]}-{dt_str[6:8]}_{dt_str[8:10]}-{dt_str[10:12]}-{dt_str[12:14]}"
        print(f"[INFO] Parsed timestamp: {timestamp}")
    else:
        timestamp = "download"
        print("[WARN] Could not parse timestamp; using fallback")

    output_dir = base_output_dir / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    dest_path = output_dir / zip_filename
    await download.save_as(dest_path)

    print(f"[INFO] Extracting ZIP to: {output_dir}")
    shutil.unpack_archive(dest_path, output_dir)
    dest_path.unlink()
    print(f"[SUCCESS] Extraction complete to: {output_dir}")

    # Return so caller can write manifest with the view context
    return output_dir, zip_filename, timestamp

async def run_task(view):
    try:
        parent_folder_name = build_view_key(view)  # canonical key (handles µ → m, etc.)
        base_output_dir = OUTPUT_BASE_DIR / parent_folder_name
    except KeyError as e:
        print(f"[FAIL] Skipping view, missing a required key: {e}")
        return

    print(f"\n{'='*25}\n[START] Processing: {parent_folder_name}\n{'='*25}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=250)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()

        try:
            await page.goto(HOMEPAGE_URL, wait_until="load", timeout=60_000)
            async with context.expect_page() as new_page_info:
                await page.locator('li#menu-item-5171 > a:has-text("Real-Time Data")').click()
                await page.locator('li#menu-item-6391 > a:has-text("SLIDER")').click()
            slider_page = await new_page_info.value
            await page.close()

            await slider_page.wait_for_load_state("networkidle", timeout=60_000)
            await slider_page.locator("#satelliteSelectorChange-button").wait_for(state="visible", timeout=60_000)

            await select_dropdown_option(slider_page, "satelliteSelectorChange-button", view["sat"])
            await select_dropdown_option(slider_page, "sectorSelectorChange-button", view["sec"])
            await select_dropdown_option(slider_page, "productSelectorChange-button", view["im"])
            await select_dropdown_option(slider_page, "numberOfImagesSelectorChange-button", view.get("num", "60"))
            await select_dropdown_option(slider_page, "timeStepSelectorChange-button", view.get("step", "10 min"))

            await slider_page.reload(wait_until="load")
            await slider_page.wait_for_timeout(3000)

            # Download/extract and get paths for manifest
            output_dir, zip_filename, timestamp = await perform_download_with_timestamp(slider_page, base_output_dir)

            # Build and write manifest.json
            pngs = sorted([p.name for p in output_dir.glob("*.png")])
            manifest = {
                "view_key": parent_folder_name,
                "view": {
                    "sat": view["sat"],
                    "sec": view["sec"],
                    "im": view["im"],
                    "num": view.get("num", "60"),
                    "step": view.get("step", "10 min"),
                },
                "source": {
                    "zip_filename": zip_filename,
                    "parsed_timestamp": timestamp
                },
                "frames": [
                    {"index": i, "original": name, "standardized": f"frame_{i:03d}.png"}
                    for i, name in enumerate(pngs)
                ]
            }
            with open(output_dir / "manifest.json", "w", encoding="utf-8") as mf:
                json.dump(manifest, mf, ensure_ascii=False, indent=2)
            print(f"[INFO] Wrote manifest: {output_dir/'manifest.json'}")

        except Exception as e:
            print(f"[FATAL ERROR] {parent_folder_name}: {e}")
            try:
                await slider_page.screenshot(path=OUTPUT_BASE_DIR / f"{parent_folder_name}_error.png")
            except Exception:
                pass
        finally:
            await browser.close()
            print(f"[END] {parent_folder_name}")

async def main():
    try:
        with open(VIEWS_JSON_PATH, 'r', encoding='utf-8') as f:
            views = json.load(f)
    except Exception as e:
        print(f"[ERROR] Failed to load {VIEWS_JSON_PATH}: {e}")
        return

    for view in views:
        await run_task(view)

    print("\n[OK] All views processed.")

if __name__ == "__main__":
    asyncio.run(main())
