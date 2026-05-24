"""
Test script to verify the fixed scraper works with a real Google Maps listing.
Uses a well-known business that definitely has Google Maps reviews.
"""
import asyncio
import json
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Import from project
from app.services.scraping.google_reviews import scrape_google_reviews
from app.core.config import settings

# Override to limit for testing
settings.max_scroll_attempts = 5
settings.max_reviews_per_company = 20


async def test_scrape(company_name: str, maps_url: str):
    logger.info("=" * 60)
    logger.info("Testing scraper for: %s", company_name)
    logger.info("URL: %s", maps_url)
    logger.info("=" * 60)

    reviews = await scrape_google_reviews(company_name, maps_url)

    logger.info("=" * 60)
    logger.info("RESULTS: %d reviews scraped", len(reviews))
    logger.info("=" * 60)

    if reviews:
        for i, r in enumerate(reviews[:5]):
            logger.info("Review %d:", i + 1)
            logger.info("  Name: %s", r.get("reviewer_name"))
            logger.info("  Rating: %s", r.get("rating"))
            logger.info("  Date: %s", r.get("review_date"))
            text = r.get("review_text", "") or ""
            logger.info("  Text: %s", text[:120] + ("..." if len(text) > 120 else ""))
            logger.info("")
    else:
        logger.error("NO REVIEWS SCRAPED — the scraper is still broken")

    return reviews


if __name__ == "__main__":
    # Use a known business with reviews. Try Freshworks (tech company in Chennai with Google Maps listing)
    # Or provide your own URL as argument:
    #   python test_scraper_fixed.py "Company Name" "https://www.google.com/maps/place/..."
    if len(sys.argv) >= 3:
        name = sys.argv[1]
        url = sys.argv[2]
    else:
        # Default: use a well-known company with reviews on Google Maps
        name = "Freshworks"
        url = "https://www.google.com/maps/place/Freshworks"

    asyncio.run(test_scrape(name, url))
