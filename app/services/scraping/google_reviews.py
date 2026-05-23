import re
import logging
from typing import AsyncIterator

from app.core.config import settings
from app.services.scraping.playwright_helpers import (
    get_browser_context,
    human_delay,
    random_scroll,
)

logger = logging.getLogger(__name__)

REVIEW_SECTION_SELECTOR = 'button[aria-label*="Reviews"]'
REVIEWS_CONTAINER = 'div[role="main"] div[role="feed"]'
REVIEW_CARD = 'div[role="feed"] > div'
REVIEW_NAME_SELECTOR = '.d4r55'
REVIEW_RATING_SELECTOR = '.kvMYJc'
REVIEW_TEXT_SELECTOR = '.w8nwRe, .MyEned, .wiI7pd'
REVIEW_DATE_SELECTOR = '.rsqaWe'


async def scrape_google_reviews(company_name: str, maps_url: str) -> list[dict]:
    context = await get_browser_context()
    page = await context.new_page()

    reviews_data: list[dict] = []
    seen_signatures: set[str] = set()
    no_new_reviews_count = 0
    max_no_new = 5

    try:
        logger.info("Navigating to %s", maps_url)
        await page.goto(maps_url, wait_until="domcontentloaded", timeout=30000)
        await human_delay(2.0, 4.0)

        try:
            await page.wait_for_selector(REVIEW_SECTION_SELECTOR, timeout=10000)
            await page.click(REVIEW_SECTION_SELECTOR)
            logger.info("Clicked reviews section")
            await human_delay(2.0, 3.0)
        except Exception as e:
            logger.warning("Could not click reviews section: %s", e)
            await page.close()
            return reviews_data

        try:
            await page.wait_for_selector(REVIEWS_CONTAINER, timeout=10000)
            logger.info("Reviews container found")
        except Exception as e:
            logger.warning("Reviews container not found: %s", e)
            await page.close()
            return reviews_data

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

            await random_scroll(page, REVIEWS_CONTAINER)

    except Exception as e:
        logger.error("Scraping failed for %s: %s", company_name, e, exc_info=True)
    finally:
        await page.close()

    return reviews_data


async def _extract_visible_reviews(page) -> list[dict]:
    return await page.evaluate(
        """
        () => {
            const reviews = [];
            const cards = document.querySelectorAll('div[role="feed"] > div');
            cards.forEach(card => {
                const nameEl = card.querySelector('.d4r55');
                const ratingEl = card.querySelector('.kvMYJc');
                const textEl = card.querySelector('.w8nwRe, .MyEned, .wiI7pd');
                const dateEl = card.querySelector('.rsqaWe');

                let reviewText = '';
                if (textEl) {
                    if (textEl.classList.contains('w8nwRe')) {
                        textEl.click();
                    }
                    reviewText = textEl.innerText.trim();
                }

                const ratingAttr = ratingEl ? ratingEl.getAttribute('aria-label') : '';
                const ratingMatch = ratingAttr.match(/(\\d+)/);
                const rating = ratingMatch ? parseInt(ratingMatch[1]) : null;

                reviews.push({
                    reviewer_name: nameEl ? nameEl.innerText.trim() : null,
                    rating: rating,
                    review_text: reviewText,
                    review_date: dateEl ? dateEl.innerText.trim() : null,
                });
            });
            return reviews;
        }
    """
    )


def _review_signature(review: dict) -> str:
    return f"{review.get('reviewer_name', '')}|{review.get('review_text', '')[:100]}|{review.get('review_date', '')}"
