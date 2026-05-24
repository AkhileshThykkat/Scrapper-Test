"""
Standalone diagnostic script to test the Playwright scraping pipeline
outside of Celery. This isolates whether the problem is:
  1. Playwright/browser lifecycle
  2. Google Maps selectors being stale
  3. Celery async integration
"""
import asyncio
import json
import logging
import sys

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Use a known Google Maps business URL for testing
# Gallabox Google Maps listing
TEST_URL = "https://www.google.com/maps/place/Gallabox"

# Current selectors from the project
SELECTORS = {
    "review_tab": 'button[aria-label*="Reviews"]',
    "reviews_container": 'div[role="main"] div[role="feed"]',
    "review_card": 'div[role="feed"] > div',
    "reviewer_name": ".d4r55",
    "rating": ".kvMYJc",
    "review_text": ".w8nwRe, .MyEned, .wiI7pd",
    "review_date": ".rsqaWe",
}


async def diagnose_scraping(url: str):
    logger.info("=== Starting Playwright Diagnostic ===")

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=True,
        args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
    )
    context = await browser.new_context(
        viewport={"width": 1280, "height": 800},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    )
    page = await context.new_page()

    # Step 1: Navigate
    logger.info("STEP 1: Navigating to %s", url)
    try:
        response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        logger.info("  Response status: %s", response.status if response else "None")
        logger.info("  Final URL: %s", page.url)
    except Exception as e:
        logger.error("  FAILED to navigate: %s", e)
        await page.screenshot(path="debug_step1_nav_fail.png")
        await browser.close()
        await pw.stop()
        return

    await asyncio.sleep(3)  # Let page settle
    await page.screenshot(path="debug_step1_loaded.png")
    logger.info("  Screenshot saved: debug_step1_loaded.png")

    # Check for consent/cookie dialogs
    logger.info("STEP 1b: Checking for consent dialogs...")
    consent_selectors = [
        'button[aria-label*="Accept"]',
        'button[aria-label*="Reject"]',
        'form[action*="consent"] button',
        'button:has-text("Accept all")',
        'button:has-text("Reject all")',
    ]
    for sel in consent_selectors:
        try:
            el = await page.wait_for_selector(sel, timeout=2000)
            if el:
                logger.info("  Found consent button: %s — clicking it", sel)
                await el.click()
                await asyncio.sleep(2)
                break
        except Exception:
            pass

    # Step 2: Find Reviews tab
    logger.info("STEP 2: Looking for Reviews tab with selector: %s", SELECTORS["review_tab"])
    try:
        await page.wait_for_selector(SELECTORS["review_tab"], timeout=10000)
        logger.info("  ✅ Reviews tab FOUND")
        await page.click(SELECTORS["review_tab"])
        logger.info("  Clicked reviews tab")
        await asyncio.sleep(3)
    except Exception as e:
        logger.error("  ❌ Reviews tab NOT FOUND: %s", e)
        # Try alternative selectors
        logger.info("  Trying alternative selectors for reviews tab...")
        alt_selectors = [
            'button[aria-label*="review"]',
            'button[data-tab-index="1"]',
            'a[aria-label*="Reviews"]',
            'a[href*="reviews"]',
            '[role="tab"]:has-text("Reviews")',
            'button:has-text("Reviews")',
            'div[role="tablist"] button',
        ]
        found = False
        for alt in alt_selectors:
            try:
                el = await page.wait_for_selector(alt, timeout=3000)
                if el:
                    text = await el.inner_text()
                    logger.info("  ✅ Alternative found: %s (text: '%s')", alt, text)
                    await el.click()
                    found = True
                    await asyncio.sleep(3)
                    break
            except Exception:
                pass
        if not found:
            logger.error("  ❌ No alternative reviews tab found either")

    await page.screenshot(path="debug_step2_reviews_tab.png")
    logger.info("  Screenshot saved: debug_step2_reviews_tab.png")

    # Step 3: Find reviews container
    logger.info("STEP 3: Looking for reviews container: %s", SELECTORS["reviews_container"])
    try:
        await page.wait_for_selector(SELECTORS["reviews_container"], timeout=10000)
        logger.info("  ✅ Reviews container FOUND")
    except Exception as e:
        logger.error("  ❌ Reviews container NOT FOUND: %s", e)
        # Try alternatives
        alt_containers = [
            'div[role="feed"]',
            'div[data-review-id]',
            '.jftiEf',
            '.fontBodyMedium',
        ]
        for alt in alt_containers:
            try:
                el = await page.wait_for_selector(alt, timeout=3000)
                if el:
                    logger.info("  ✅ Alternative container found: %s", alt)
                    break
            except Exception:
                pass

    # Step 4: Try to extract reviews with CURRENT selectors
    logger.info("STEP 4: Extracting reviews with CURRENT selectors...")
    cards = await page.query_selector_all(SELECTORS["review_card"])
    logger.info("  Cards found with '%s': %d", SELECTORS["review_card"], len(cards))

    for sel_name, sel_val in SELECTORS.items():
        if sel_name in ("review_tab", "reviews_container", "review_card"):
            continue
        elements = await page.query_selector_all(sel_val)
        logger.info("  '%s' (%s): %d elements", sel_name, sel_val, len(elements))

    # Step 5: Dump actual DOM structure of review area
    logger.info("STEP 5: Analyzing actual DOM structure of review area...")
    dom_info = await page.evaluate("""
        () => {
            const result = {};

            // Check for feed
            const feed = document.querySelector('div[role="feed"]');
            result.has_feed = !!feed;
            if (feed) {
                result.feed_children = feed.children.length;
                result.feed_child_tags = Array.from(feed.children).slice(0, 5).map(c => ({
                    tag: c.tagName,
                    classes: c.className.split(' ').filter(Boolean).slice(0, 10),
                    role: c.getAttribute('role'),
                    childCount: c.children.length,
                }));
            }

            // Look for review-like elements with different selectors
            const possibleReviewSelectors = [
                'div[data-review-id]',
                '.jftiEf',
                '.WMbnJf',
                '[data-review-id]',
                '.GHT2ce',
                '.DUGVrf',
            ];
            result.alternative_matches = {};
            for (const sel of possibleReviewSelectors) {
                result.alternative_matches[sel] = document.querySelectorAll(sel).length;
            }

            // Sample first review card's inner HTML classes
            if (feed && feed.children.length > 0) {
                const firstCard = feed.children[0];
                const allClasses = new Set();
                firstCard.querySelectorAll('*').forEach(el => {
                    el.classList.forEach(cls => allClasses.add(cls));
                });
                result.first_card_classes = Array.from(allClasses).sort();

                // Find elements that look like they contain text
                const textEls = firstCard.querySelectorAll('span, div');
                result.text_elements_sample = Array.from(textEls).slice(0, 20).map(el => ({
                    tag: el.tagName,
                    classes: Array.from(el.classList),
                    text: el.innerText?.substring(0, 80),
                    ariaLabel: el.getAttribute('aria-label')?.substring(0, 80),
                }));
            }

            return result;
        }
    """)

    logger.info("  DOM Analysis:")
    logger.info("    Has feed: %s", dom_info.get("has_feed"))
    logger.info("    Feed children: %s", dom_info.get("feed_children"))

    if dom_info.get("feed_child_tags"):
        logger.info("    First few feed children:")
        for child in dom_info["feed_child_tags"]:
            logger.info("      %s classes=%s role=%s children=%s",
                        child["tag"], child["classes"], child["role"], child["childCount"])

    logger.info("    Alternative selector matches:")
    for sel, count in dom_info.get("alternative_matches", {}).items():
        logger.info("      %s: %d", sel, count)

    if dom_info.get("first_card_classes"):
        logger.info("    First card CSS classes: %s", dom_info["first_card_classes"])

    if dom_info.get("text_elements_sample"):
        logger.info("    Text elements in first card:")
        for el in dom_info["text_elements_sample"][:15]:
            if el.get("text") and len(el["text"].strip()) > 0:
                logger.info("      <%s class='%s'> %s",
                            el["tag"], " ".join(el["classes"]), el["text"][:60])

    # Step 6: Try the JS extraction function from the project
    logger.info("STEP 6: Running the project's JS extraction function...")
    extracted = await page.evaluate("""
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
    """)
    logger.info("  Extracted with current selectors: %d reviews", len(extracted))
    if extracted:
        logger.info("  First review: %s", json.dumps(extracted[0], indent=2))
    else:
        logger.info("  ❌ ZERO reviews extracted — selectors are STALE")

    await page.screenshot(path="debug_step6_final.png")
    logger.info("  Screenshot saved: debug_step6_final.png")

    # Save full page HTML for offline analysis
    html = await page.content()
    with open("debug_page_source.html", "w", encoding="utf-8") as f:
        f.write(html)
    logger.info("  Full page HTML saved: debug_page_source.html")

    await browser.close()
    await pw.stop()
    logger.info("=== Diagnostic Complete ===")


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else TEST_URL
    asyncio.run(diagnose_scraping(url))
