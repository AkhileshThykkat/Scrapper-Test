import logging

from app.core.config import settings
from app.services.scraping.playwright_helpers import (
    get_browser_context,
    human_delay,
    random_scroll,
)

logger = logging.getLogger(__name__)

# Reviews tab — try multiple selector strategies
REVIEW_TAB_SELECTORS = [
    '[role="tab"]:has-text("Reviews")',
    'button[aria-label*="Reviews for"]',
    'button:has-text("Reviews")',
]

# Scrollable panel containing reviews (Google Maps 2024-2026)
REVIEWS_CONTAINER = "div[role='main']"
REVIEWS_CONTAINER_FALLBACK = ".m6QErb"

# Individual review elements (Semantic/Attributes instead of CSS classes)
REVIEW_CARD = "button[aria-label^='Share '][aria-label*='review']"
REVIEW_MORE_BUTTON = "button[aria-label*='See more']"


async def scrape_google_reviews(company_name: str, maps_url: str) -> list[dict]:
    async with get_browser_context() as context:
        page = await context.new_page()
        reviews_data: list[dict] = []
        seen_signatures: set[str] = set()
        no_new_reviews_count = 0
        max_no_new = 5

        try:
            logger.info("Navigating to %s", maps_url)
            await page.goto(maps_url, wait_until="domcontentloaded", timeout=30000)
            await human_delay(3.0, 5.0)

            # Handle consent/cookie dialogs
            await _dismiss_consent(page)

            # Wait for the page to fully render (Google Maps is SPA)
            # networkidle is unreliable here because Maps constantly polls
            await human_delay(2.0, 4.0)

            # Check if we are already on the reviews tab (e.g. the URL specifically pointed to it)
            already_on_reviews = False
            try:
                # 'Sort reviews' button only exists when the Reviews tab is active
                sort_btn = await page.wait_for_selector("button[aria-label*='Sort reviews']", timeout=3000)
                if sort_btn:
                    already_on_reviews = True
                    logger.info("Already on reviews tab (found Sort button).")
            except Exception:
                pass

            if not already_on_reviews:
                # Click the Reviews tab
                if not await _click_reviews_tab(page):
                    logger.warning("Could not find or click Reviews tab for %s. Saving screenshot.", company_name)
                    await page.screenshot(path=f"/home/akhileshmt/Documents/Scrapper-Test/failed_scrape_{company_name.replace(' ', '_')}.png")
                    return reviews_data
                await human_delay(2.0, 3.0)

            # Find the scrollable reviews container
            container_sel = await _find_reviews_container(page)
            if not container_sel:
                logger.warning("Reviews container not found for %s", company_name)
                return reviews_data

            logger.info("Reviews container found: %s", container_sel)

            # Expand all "More" buttons before first extraction
            await _expand_all_reviews(page)

            for attempt in range(settings.max_scroll_attempts):
                if len(reviews_data) >= settings.max_reviews_per_company:
                    logger.info("Reached max reviews (%d)", settings.max_reviews_per_company)
                    break

                extracted = await _extract_visible_reviews(page)
                new_count = 0

                for review in extracted:
                    sig = _review_signature(review)
                    if sig not in seen_signatures:
                        seen_signatures.add(sig)
                        reviews_data.append(review)
                        new_count += 1

                logger.info(
                    "Scroll %d: found %d new reviews (total %d)",
                    attempt + 1,
                    new_count,
                    len(reviews_data),
                )

                if new_count == 0:
                    no_new_reviews_count += 1
                    if no_new_reviews_count >= max_no_new:
                        logger.info("No new reviews for %d scrolls, stopping", max_no_new)
                        break
                else:
                    no_new_reviews_count = 0

                await random_scroll(page, container_sel)

                # After each scroll, try to expand new "More" buttons
                await _expand_all_reviews(page)

        except Exception as e:
            logger.error("Scraping failed for %s: %s", company_name, e, exc_info=True)
        finally:
            await page.close()

    return reviews_data


async def _dismiss_consent(page):
    """Dismiss Google consent/cookie dialogs if present."""
    consent_selectors = [
        'button[aria-label*="Accept" i]',
        'button:has-text("Accept all")',
        'button:has-text("Reject all")',
        'form[action*="consent"] button',
    ]
    for sel in consent_selectors:
        try:
            el = await page.wait_for_selector(sel, timeout=3000)
            if el:
                logger.info("Dismissing consent dialog: %s", sel)
                await el.click()
                await human_delay(1.0, 2.0)
                return
        except Exception:
            pass


async def _click_reviews_tab(page) -> bool:
    """Try to click the Reviews tab using Playwright's built-in locators."""
    try:
        import re
        # This will look for a tab whose accessible name contains "Reviews" (e.g. "Reviews", "Reviews for AiSensy")
        tab = page.get_by_role("tab", name=re.compile("Reviews", re.IGNORECASE))
        
        # Wait for it to be visible and click it
        await tab.first.wait_for(state="visible", timeout=8000)
        logger.info("Found Reviews tab via get_by_role!")
        await tab.first.click()
        return True
    except Exception as e:
        logger.error(f"Failed to find or click Reviews tab via get_by_role: {e}")

    # Fallback to older CSS approach just in case
    for sel in REVIEW_TAB_SELECTORS:
        try:
            el = await page.wait_for_selector(sel, timeout=5000)
            if el:
                text = await el.inner_text()
                if text and "write" in text.lower():
                    continue
                logger.info("Found reviews tab candidate via fallback: '%s' via %s", text.strip() if text else "N/A", sel)
                await el.click()
                return True
        except Exception as e:
            logger.debug(f"Selector {sel} failed: {e}")
            continue

    logger.warning("No reviews tab found with any selector")
    return False


async def _find_reviews_container(page) -> str | None:
    """Find the scrollable reviews container."""
    for sel in [REVIEWS_CONTAINER, REVIEWS_CONTAINER_FALLBACK]:
        try:
            el = await page.wait_for_selector(sel, timeout=8000)
            if el:
                return sel
        except Exception:
            continue
    return None


async def _expand_all_reviews(page):
    """Click all 'More' buttons to expand truncated review text."""
    try:
        more_buttons = await page.query_selector_all(REVIEW_MORE_BUTTON)
        for btn in more_buttons:
            try:
                await btn.click()
            except Exception:
                pass
        if more_buttons:
            await human_delay(0.3, 0.5)
    except Exception:
        pass


async def _extract_visible_reviews(page) -> list[dict]:
    """Extract review data from currently visible review cards using JS evaluation."""
    return await page.evaluate(
        """
        () => {
            const reviews = [];
            // Every review has a "Share [Name]'s review" button for screen readers.
            const shareBtns = document.querySelectorAll('button[aria-label^="Share "][aria-label*="review"]');
            
            shareBtns.forEach(btn => {
                // The review card is usually 3-5 levels up. 
                // We find the closest ancestor that contains a "stars" label.
                let card = btn.parentElement;
                while (card && !card.querySelector('[aria-label*="stars"]')) {
                    card = card.parentElement;
                    if (card === document.body) { card = null; break; }
                }
                if (!card) return; // Skip if we can't find the card container

                // Find rating
                const ratingEl = card.querySelector('[aria-label*="stars"]');
                let rating = null;
                if (ratingEl) {
                    const match = ratingEl.getAttribute('aria-label').match(/(\\d+)/);
                    if (match) rating = parseInt(match[1]);
                }

                // Name from "Photo of [Name]" (Google always includes this for the avatar)
                const photoBtn = card.querySelector('button[aria-label^="Photo of "]');
                let name = null;
                if (photoBtn) {
                    name = photoBtn.getAttribute('aria-label').replace('Photo of ', '').trim();
                }

                // Text: we look for a span with length > 20 that doesn't have a button inside
                let reviewText = null;
                const textNodes = card.querySelectorAll('span');
                for (const node of textNodes) {
                    if (node.innerText && node.innerText.length > 20 && !node.querySelector('button')) {
                        reviewText = node.innerText.trim();
                    }
                }

                // Date: "ago", "day", "month", "year"
                let date = null;
                const spans = card.querySelectorAll('span');
                for (const span of spans) {
                    const text = span.innerText;
                    if (text && (text.includes('ago') || text.includes('day') || text.includes('month') || text.includes('year'))) {
                        date = text.trim();
                        break;
                    }
                }

                reviews.push({
                    reviewer_name: name || "Unknown",
                    rating: rating,
                    review_text: reviewText,
                    review_date: date,
                });
            });
            return reviews;
        }
    """
    )


def _review_signature(review: dict) -> str:
    name = review.get("reviewer_name", "") or ""
    text = (review.get("review_text", "") or "")[:100]
    date = review.get("review_date", "") or ""
    return f"{name}|{text}|{date}"
