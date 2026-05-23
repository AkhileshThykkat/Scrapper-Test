import asyncio
import random
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from app.core.config import settings

_browser: Browser | None = None
_context: BrowserContext | None = None


async def get_browser_context() -> BrowserContext:
    global _browser, _context
    if _context is not None and _context.is_connected():
        return _context
    if _browser is not None and _browser.is_connected():
        _context = await _browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        return _context
    _playwright = await async_playwright().start()
    _browser = await _playwright.chromium.launch(
        headless=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
        ],
    )
    _context = await _browser.new_context(
        viewport={"width": 1280, "height": 800},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    )
    return _context


async def close_browser():
    global _browser, _context
    if _context is not None:
        await _context.close()
        _context = None
    if _browser is not None:
        await _browser.close()
        _browser = None


async def human_delay(min_s: float = None, max_s: float = None):
    min_s = min_s or settings.scrape_delay_min
    max_s = max_s or settings.scrape_delay_max
    await asyncio.sleep(random.uniform(min_s, max_s))


async def random_scroll(page: Page, container_selector: str | None = None):
    delta = random.randint(300, 800)
    if container_selector:
        await page.evaluate(
            f"document.querySelector('{container_selector}').scrollBy(0, {delta});"
        )
    else:
        await page.evaluate(f"window.scrollBy(0, {delta});")
    await human_delay(0.5, 1.5)
