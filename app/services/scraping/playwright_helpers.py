import asyncio
import random
from contextlib import asynccontextmanager
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from app.core.config import settings


@asynccontextmanager
async def get_browser_context():
    """
    Context manager that creates a fresh Playwright browser + context for each
    scraping session and ensures cleanup. This replaces the broken global
    singleton pattern which failed in Celery workers because each task
    creates/destroys its own asyncio event loop via _run_async().
    """
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(
        headless=False,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ],
    )
    context = await browser.new_context(
        viewport={"width": 1280, "height": 900},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        locale="en-US",
        timezone_id="America/New_York",
    )
    try:
        yield context
    finally:
        await context.close()
        await browser.close()
        await playwright.stop()


async def human_delay(min_s: float = None, max_s: float = None):
    min_s = min_s or settings.scrape_delay_min
    max_s = max_s or settings.scrape_delay_max
    await asyncio.sleep(random.uniform(min_s, max_s))


async def random_scroll(page: Page, container_selector: str | None = None):
    delta = random.randint(300, 800)
    if container_selector:
        await page.evaluate(
            """(selector) => {
                const el = document.querySelector(selector);
                if (el) el.scrollBy(0, %d);
            }""" % delta,
            container_selector,
        )
    else:
        await page.evaluate(f"window.scrollBy(0, {delta});")
    await human_delay(0.5, 1.5)
