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
    'button[aria-label*="review" i]',
    'button[aria-label*="Review"]',
    'button[data-tab-index="1"]',
    '[role="tab"]:has-text("Reviews")',
    'button:has-text("Reviews")',
]

# Scrollable panel containing reviews (Google Maps 2024-2026)
REVIEWS_CONTAINER = ".m6QErb.DxyBCb.kA9KIf.dS8AEf"
REVIEWS_CONTAINER_FALLBACK = ".m6QErb"

# Individual review elements (verified May 2026)
REVIEW_CARD = ".jftiEf"
REVIEW_NAME_SELECTOR = ".d4r55"
REVIEW_RATING_SELECTOR = ".kvMYJc"
REVIEW_TEXT_SELECTOR = ".wiI7pd"
REVIEW_MORE_BUTTON = ".w8nwRe"
REVIEW_DATE_SELECTOR = ".rsqaWe"


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
            await page.wait_for_load_state("networkidle", timeout=15000)
            await human_delay(1.0, 2.0)

            # Click the Reviews tab
            if not await _click_reviews_tab(page):
                logger.warning("Could not find or click Reviews tab for %s", company_name)
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
    """Try multiple selectors to find and click the Reviews tab."""
    for sel in REVIEW_TAB_SELECTORS:
        try:
            el = await page.wait_for_selector(sel, timeout=5000)
            if el:
                # Verify it's actually the reviews tab (not some other button)
                text = await el.inner_text()
                logger.info("Found reviews tab candidate: '%s' via %s", text.strip(), sel)
                await el.click()
                return True
        except Exception:
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
            const cards = document.querySelectorAll('.jftiEf');
            cards.forEach(card => {
                const nameEl = card.querySelector('.d4r55');
                const ratingEl = card.querySelector('.kvMYJc');
                const textEl = card.querySelector('.wiI7pd');
                const dateEl = card.querySelector('.rsqaWe');

                let reviewText = '';
                if (textEl) {
                    reviewText = textEl.innerText.trim();
                }

                // Extract rating from aria-label like "5 stars" or "4 stars"
                const ratingAttr = ratingEl ? ratingEl.getAttribute('aria-label') : '';
                const ratingMatch = ratingAttr ? ratingAttr.match(/(\\d+)/) : null;
                const rating = ratingMatch ? parseInt(ratingMatch[1]) : null;

                reviews.push({
                    reviewer_name: nameEl ? nameEl.innerText.trim() : null,
                    rating: rating,
                    review_text: reviewText || null,
                    review_date: dateEl ? dateEl.innerText.trim() : null,
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
