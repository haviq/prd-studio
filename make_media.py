"""Generate product screenshots and a demo video for the PRD Studio landing."""
import os, sys, time, pathlib
from playwright.sync_api import sync_playwright

CHROME = '/a0/tmp/playwright/chromium-1228/chrome-linux64/chrome'
BASE = os.environ.get('SITE', 'https://prd.haaviq.dev')
OUT = pathlib.Path(__file__).parent / 'static'
VID = pathlib.Path('/tmp/prd_video')
VID.mkdir(exist_ok=True)
for p in VID.glob('*'):
    p.unlink()


def shot(page, name, full=False):
    page.screenshot(path=str(OUT / name), full_page=full)
    print('shot', name, flush=True)


with sync_playwright() as pw:
    b = pw.chromium.launch(executable_path=CHROME, args=['--no-sandbox'])
    ctx = b.new_context(viewport={'width': 1280, 'height': 800}, device_scale_factor=1,
                        record_video_dir=str(VID), record_video_size={'width': 1280, 'height': 800})
    page = ctx.new_page()

    # 1. landing hero
    page.goto(BASE + '/', wait_until='networkidle')
    time.sleep(1.2)
    shot(page, 'shot-home.png')

    # 2. pricing
    page.goto(BASE + '/pricing', wait_until='networkidle')
    time.sleep(1.0)
    shot(page, 'shot-pricing.png')

    # 3. docs
    page.goto(BASE + '/docs', wait_until='networkidle')
    time.sleep(1.0)
    shot(page, 'shot-docs.png')

    # 4. studio
    page.goto(BASE + '/studio', wait_until='networkidle')
    time.sleep(1.0)
    shot(page, 'shot-studio.png')

    # ---- demo video: a scripted tour ----
    page.goto(BASE + '/', wait_until='networkidle')
    time.sleep(1.5)
    page.mouse.wheel(0, 500); time.sleep(1.0)
    page.mouse.wheel(0, 600); time.sleep(1.0)
    page.mouse.wheel(0, 900); time.sleep(1.2)
    page.mouse.wheel(0, 900); time.sleep(1.0)
    page.goto(BASE + '/studio', wait_until='networkidle')
    time.sleep(1.0)
    page.fill('#name', 'Scrapling')
    time.sleep(0.4)
    page.fill('#desc', 'AI web scraping platform that turns any site into structured data')
    time.sleep(0.5)
    page.fill('#feat', 'bulk scrape\nexport CSV\nscheduled monitoring')
    time.sleep(0.6)
    page.mouse.wheel(0, 300); time.sleep(1.0)
    page.goto(BASE + '/docs', wait_until='networkidle')
    time.sleep(1.5)
    page.mouse.wheel(0, 700); time.sleep(1.5)
    page.mouse.wheel(0, -700); time.sleep(0.8)
    page.goto(BASE + '/pricing', wait_until='networkidle')
    time.sleep(1.8)

    ctx.close()
    b.close()

print('video dir:', list(VID.glob('*.webm')), flush=True)
