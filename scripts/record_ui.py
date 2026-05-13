"""
Record an OmniDub Web UI walkthrough using Playwright headless + video.

Flow captured:
  1. Land on the page.
  2. Tap "Choose a clip" — upload samples/source_en.mp4.
  3. Select target language (中文 already selected by default).
  4. Leave voice mode as "Clone each speaker".
  5. Tap "Dub it".
  6. Progress stages animate as SSE events arrive.
  7. The final video preview appears — we capture that too.

Output: docs/assets/ui_walkthrough.webm (converted to mp4 later).
"""

from __future__ import annotations
import asyncio
import os
import sys
from pathlib import Path

from playwright.async_api import async_playwright


ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "samples" / "source_en.mp4"
OUT_DIR = ROOT / "docs" / "assets"
OUT_DIR.mkdir(parents=True, exist_ok=True)

VIEWPORT = {"width": 430, "height": 932}    # iPhone 14 Pro Max size → mobile-first showcase


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--disable-dev-shm-usage", "--no-sandbox"],
        )
        ctx = await browser.new_context(
            viewport=VIEWPORT,
            device_scale_factor=2,
            record_video_dir=str(OUT_DIR),
            record_video_size=VIEWPORT,
        )
        page = await ctx.new_page()

        # 1. land
        await page.goto("http://127.0.0.1:8080/", wait_until="networkidle")
        await asyncio.sleep(1.2)

        # 2. upload (set file on hidden input directly)
        await page.set_input_files("#file", str(SAMPLE))
        await asyncio.sleep(1.0)

        # 3. language chip (中文 is default but tap it explicitly for visual feedback)
        await page.click('#langs button[data-v="zh"]')
        await asyncio.sleep(0.8)
        # switch to Indonesia and back to show options
        await page.click('#langs button[data-v="id"]')
        await asyncio.sleep(0.7)
        await page.click('#langs button[data-v="zh"]')
        await asyncio.sleep(0.7)

        # 4. voice chip
        await page.click('#voice button[data-v="clone"]')
        await asyncio.sleep(0.6)

        # 5. GO
        await page.click("#go")
        # progress screen
        try:
            await page.wait_for_selector("#step-progress:not(.hide)", timeout=10_000)
        except Exception:
            pass
        # watch the stages animate up to ~40s (long enough to see multiple ticks)
        for _ in range(40):
            await asyncio.sleep(1.0)
            done = await page.evaluate("document.getElementById('step-done').classList.contains('hide') === false")
            if done:
                break

        # 6. if the UI completed, linger on the result
        await asyncio.sleep(3.0)

        await ctx.close()
        await browser.close()

        # Playwright writes a .webm per page; pick newest file
        latest = sorted(OUT_DIR.glob("*.webm"), key=lambda p: p.stat().st_mtime)[-1]
        target = OUT_DIR / "ui_walkthrough.webm"
        if latest != target:
            latest.replace(target)
        print(f"recorded → {target}")


if __name__ == "__main__":
    asyncio.run(main())
