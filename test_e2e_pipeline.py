"""
End-to-end pipeline test via the live API + Celery.

Prerequisites (run in 3 separate terminals):
  Terminal 1 — FastAPI:
    uv run uvicorn app.main:app --reload --port 8000

  Terminal 2 — Celery worker (both queues):
    uv run celery -A app.workers.celery_app worker -Q scrape_queue,analysis_queue -l info

  Terminal 3 — Run this script:
    uv run python test_e2e_pipeline.py

What it does:
  1. Creates a company via POST /api/v1/companies
  2. Inserts sample reviews directly into DB (simulates scraping)
  3. Triggers analysis via POST /api/v1/companies/{id}/analyze
  4. Polls until analysis completes
  5. Fetches and prints insights from GET /api/v1/companies/{id}/insights
"""
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

API_BASE = "http://localhost:8000/api/v1"


def load_reviews(filepath: str) -> list[str]:
    text = Path(filepath).read_text()
    return [r.strip() for r in text.split("---") if r.strip()]


async def insert_reviews_to_db(company_id: int, reviews: list[str]):
    """Insert reviews directly into DB to simulate scraping."""
    from app.db.session import async_session_factory
    from app.models.review import Review
    from app.utils.dedup import generate_content_hash
    from sqlalchemy import select

    async with async_session_factory() as session:
        inserted = 0
        for i, text in enumerate(reviews):
            content_hash = generate_content_hash("e2e_test", f"User_{i+1}", text, "2024-01")

            existing = await session.execute(
                select(Review.id).where(
                    Review.company_id == company_id,
                    Review.content_hash == content_hash,
                ).limit(1)
            )
            if existing.scalar_one_or_none() is not None:
                continue

            review = Review(
                company_id=company_id,
                reviewer_name=f"User_{i+1}",
                review_text=text,
                review_date="2024-01",
                source="e2e_test",
                content_hash=content_hash,
                is_processed=False,
            )
            session.add(review)
            inserted += 1

        await session.commit()
        logger.info("Inserted %d reviews into DB", inserted)
        return inserted


async def main():
    reviews_file = sys.argv[1] if len(sys.argv) > 1 else "reviewsample.txt"
    raw_reviews = load_reviews(reviews_file)
    logger.info("Loaded %d reviews from %s", len(raw_reviews), reviews_file)

    async with httpx.AsyncClient(timeout=30) as client:
        # ── Step 1: Check API is up ──
        try:
            resp = await client.get(f"{API_BASE}/companies")
            resp.raise_for_status()
        except Exception as e:
            logger.error("❌ API not reachable at %s — is FastAPI running?", API_BASE)
            logger.error("   Start it with: uv run uvicorn app.main:app --reload --port 8000")
            sys.exit(1)

        logger.info("✅ API is up")

        # ── Step 2: Create company ──
        resp = await client.post(f"{API_BASE}/companies", json={
            "name": "E2E_TestCRM",
            "website": "https://testcrm.example.com",
            "google_maps_url": "https://www.google.com/maps/place/TestCRM",
        })

        if resp.status_code == 201:
            company = resp.json()
            logger.info("✅ Created company: %s (id=%d)", company["name"], company["id"])
        elif resp.status_code == 422:
            # Company might already exist, list and find it
            resp = await client.get(f"{API_BASE}/companies")
            companies = resp.json()["companies"]
            company = next((c for c in companies if c["name"] == "E2E_TestCRM"), None)
            if company:
                logger.info("Using existing company: %s (id=%d)", company["name"], company["id"])
            else:
                logger.error("❌ Failed to create company: %s", resp.text)
                sys.exit(1)
        else:
            resp.raise_for_status()

        company_id = company["id"]

        # ── Step 3: Insert reviews into DB ──
        inserted = await insert_reviews_to_db(company_id, raw_reviews)

        # ── Step 4: Verify reviews exist ──
        resp = await client.get(f"{API_BASE}/companies/{company_id}/reviews")
        reviews_data = resp.json()
        logger.info("✅ Reviews in DB: %d", reviews_data["total"])

        if reviews_data["total"] == 0:
            logger.error("❌ No reviews in DB, cannot proceed")
            sys.exit(1)

        # ── Step 5: Trigger analysis via Celery ──
        logger.info("Triggering analysis task via Celery...")
        resp = await client.post(f"{API_BASE}/companies/{company_id}/analyze")
        resp.raise_for_status()
        task_info = resp.json()
        logger.info("✅ Analysis task queued: task_id=%s", task_info.get("task_id"))

        # ── Step 6: Poll for insights ──
        logger.info("Waiting for Celery to complete analysis + insight generation...")
        max_wait = 180  # 3 minutes
        poll_interval = 5
        elapsed = 0

        while elapsed < max_wait:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            resp = await client.get(f"{API_BASE}/companies/{company_id}/insights")
            if resp.status_code == 200:
                insights = resp.json()
                logger.info("✅ Insights ready after %ds!", elapsed)
                break
            else:
                logger.info("  ⏳ Waiting... (%ds/%ds)", elapsed, max_wait)
        else:
            logger.error("❌ Timeout waiting for insights after %ds", max_wait)
            logger.error("   Check Celery worker logs for errors")
            sys.exit(1)

        # ── Step 7: Print results ──
        logger.info("\n" + "=" * 70)
        logger.info("✅ E2E PIPELINE COMPLETE")
        logger.info("=" * 70)

        logger.info("\n📊 STRENGTHS:")
        for s in insights.get("strengths", []):
            logger.info("  ✅ %s", s)

        logger.info("\n📊 WEAKNESSES:")
        for w in insights.get("weaknesses", []):
            logger.info("  ❌ %s", w)

        logger.info("\n📊 FEATURE REQUESTS:")
        for f in insights.get("feature_requests", []):
            logger.info("  💡 %s", f)

        logger.info("\n📊 OVERALL: %s", insights.get("overall_summary", "N/A"))

        logger.info("\n📊 REVIEW COUNTS: %d total, %d negative",
            insights.get("total_review_count", 0),
            insights.get("negative_review_count", 0))

        logger.info("\n🔴 PAIN POINTS:")
        for i, pp in enumerate(insights.get("pain_points", [])):
            if isinstance(pp, dict):
                logger.info("  %d. %s (freq=%s, severity=%s/5)",
                    i + 1, pp.get("pain_point"), pp.get("frequency"), pp.get("severity_avg"))
                for ex in pp.get("example_reviews", [])[:2]:
                    logger.info('     → "%s"', str(ex)[:100])
            else:
                logger.info("  %d. %s", i + 1, pp)

        logger.info("\n📝 PAIN POINT SUMMARY:")
        logger.info("  %s", insights.get("pain_point_summary", "N/A"))

        logger.info("\n" + "=" * 70)
        logger.info("✅ ALL DONE — Full pipeline verified!")
        logger.info("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
