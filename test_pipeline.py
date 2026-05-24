"""
End-to-end pipeline test: DB → Analysis → Insights
Bypasses scraping — inserts reviews from reviewsample.txt directly into the DB,
then runs the analysis + insight generation pipeline.
"""
import asyncio
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

from sqlalchemy import select, text

from app.db.session import async_session_factory
from app.db.base import Base
from app.models.company import Company
from app.models.review import Review
from app.models.review_analysis import ReviewAnalysis
from app.models.company_insights import CompanyInsight
from app.services.ai.analyzer import analyze_review_text
from app.services.insights.generator import generate_company_insights
from app.utils.dedup import generate_content_hash


def load_reviews(filepath: str) -> list[str]:
    text = Path(filepath).read_text()
    return [r.strip() for r in text.split("---") if r.strip()]


async def run_pipeline():
    company_name = "TestCRM"
    source = "manual_test"
    reviews_file = sys.argv[1] if len(sys.argv) > 1 else "reviewsample.txt"

    raw_reviews = load_reviews(reviews_file)
    logger.info("Loaded %d reviews from %s", len(raw_reviews), reviews_file)

    async with async_session_factory() as session:
        # ── Step 1: Create or find company ──
        result = await session.execute(select(Company).where(Company.name == company_name))
        company = result.scalar_one_or_none()

        if not company:
            company = Company(name=company_name, website="https://testcrm.example.com")
            session.add(company)
            await session.flush()
            await session.refresh(company)
            logger.info("Created company: %s (id=%d)", company.name, company.id)
        else:
            logger.info("Using existing company: %s (id=%d)", company.name, company.id)

        # ── Step 2: Insert reviews with dedup ──
        inserted = 0
        skipped = 0
        for i, review_text in enumerate(raw_reviews):
            content_hash = generate_content_hash(source, f"Reviewer_{i+1}", review_text, "2024-01")

            existing = await session.execute(
                select(Review.id).where(Review.content_hash == content_hash).limit(1)
            )
            if existing.scalar_one_or_none() is not None:
                skipped += 1
                continue

            review = Review(
                company_id=company.id,
                reviewer_name=f"Reviewer_{i+1}",
                review_text=review_text,
                review_date="2024-01",
                source=source,
                rating=None,
                content_hash=content_hash,
                is_processed=False,
            )
            session.add(review)
            inserted += 1

        await session.commit()
        logger.info("Inserted %d reviews, skipped %d duplicates", inserted, skipped)

        # ── Step 3: Analyze unprocessed reviews ──
        result = await session.execute(
            select(Review).where(
                Review.company_id == company.id,
                Review.is_processed == False,
            )
        )
        unprocessed = result.scalars().all()
        logger.info("Found %d unprocessed reviews to analyze", len(unprocessed))

        analyzed_count = 0
        for review in unprocessed:
            if not review.review_text:
                review.is_processed = True
                continue

            logger.info("Analyzing review %d/%d (id=%d)...", analyzed_count + 1, len(unprocessed), review.id)
            analysis = await analyze_review_text(review.review_text)

            review_analysis = ReviewAnalysis(
                review_id=review.id,
                sentiment=analysis.get("sentiment"),
                category=analysis.get("category"),
                short_summary=analysis.get("short_summary"),
                pain_points=analysis.get("pain_points", []),
                severity=analysis.get("severity", 0),
                embedding_vector=None,
            )
            session.add(review_analysis)
            review.is_processed = True
            analyzed_count += 1

            # Rate limit: small delay between LLM calls
            await asyncio.sleep(0.3)

        await session.commit()
        logger.info("Analyzed %d reviews", analyzed_count)

        # ── Step 4: Generate insights + pain point analysis ──
        logger.info("Generating company insights...")
        reviews_result = await session.execute(
            select(Review).where(Review.company_id == company.id)
        )
        all_reviews = reviews_result.scalars().all()

        analyses_result = await session.execute(
            select(ReviewAnalysis).where(
                ReviewAnalysis.review_id.in_([r.id for r in all_reviews])
            )
        )
        all_analyses = analyses_result.scalars().all()

        reviews_data = [
            {"id": r.id, "review_text": r.review_text, "rating": r.rating}
            for r in all_reviews
        ]
        analyses_data = [
            {
                "review_id": a.review_id,
                "sentiment": a.sentiment,
                "category": a.category,
                "pain_points": a.pain_points or [],
                "severity": a.severity or 0,
            }
            for a in all_analyses
        ]

        insights = await generate_company_insights(company.name, reviews_data, analyses_data)

        # Upsert insight
        existing = await session.execute(
            select(CompanyInsight).where(CompanyInsight.company_id == company.id)
        )
        existing_insight = existing.scalar_one_or_none()

        if existing_insight:
            existing_insight.strengths = insights.get("strengths", [])
            existing_insight.weaknesses = insights.get("weaknesses", [])
            existing_insight.feature_requests = insights.get("feature_requests", [])
            existing_insight.overall_summary = insights.get("overall_summary", "")
            existing_insight.pain_points = insights.get("pain_points", [])
            existing_insight.pain_point_summary = insights.get("pain_point_summary", "")
            existing_insight.negative_review_count = insights.get("negative_review_count", 0)
            existing_insight.total_review_count = insights.get("total_review_count", 0)
        else:
            insight = CompanyInsight(
                company_id=company.id,
                strengths=insights.get("strengths", []),
                weaknesses=insights.get("weaknesses", []),
                feature_requests=insights.get("feature_requests", []),
                overall_summary=insights.get("overall_summary", ""),
                pain_points=insights.get("pain_points", []),
                pain_point_summary=insights.get("pain_point_summary", ""),
                negative_review_count=insights.get("negative_review_count", 0),
                total_review_count=insights.get("total_review_count", 0),
            )
            session.add(insight)

        await session.commit()

        # ── Step 5: Print results ──
        logger.info("\n" + "=" * 70)
        logger.info("✅ PIPELINE COMPLETE")
        logger.info("=" * 70)

        sentiments = [a.sentiment for a in all_analyses]
        logger.info("Reviews:     %d total", len(all_reviews))
        logger.info("Positive:    %d", sentiments.count("positive"))
        logger.info("Negative:    %d", sentiments.count("negative"))
        logger.info("Mixed:       %d", sentiments.count("mixed"))
        logger.info("Neutral:     %d", sentiments.count("neutral"))

        logger.info("\n📊 STRENGTHS:")
        for s in insights.get("strengths", []):
            logger.info("  ✅ %s", s)

        logger.info("\n📊 WEAKNESSES:")
        for w in insights.get("weaknesses", []):
            logger.info("  ❌ %s", w)

        logger.info("\n🔴 TOP PAIN POINTS:")
        for i, pp in enumerate(insights.get("pain_points", [])):
            if isinstance(pp, dict):
                logger.info("  %d. %s (freq=%s, severity=%s/5)",
                    i + 1, pp.get("pain_point"), pp.get("frequency"), pp.get("severity_avg"))
            else:
                logger.info("  %d. %s", i + 1, pp)

        logger.info("\n📝 PAIN POINT SUMMARY:")
        logger.info("  %s", insights.get("pain_point_summary", "N/A"))

        # Verify DB persistence
        db_insight = await session.execute(
            select(CompanyInsight).where(CompanyInsight.company_id == company.id)
        )
        saved = db_insight.scalar_one_or_none()
        if saved:
            logger.info("\n✅ Insights persisted to DB (id=%d, company_id=%d)", saved.id, saved.company_id)
            logger.info("  pain_points count: %d", len(saved.pain_points or []))
            logger.info("  negative_review_count: %d", saved.negative_review_count)
            logger.info("  total_review_count: %d", saved.total_review_count)
        else:
            logger.error("❌ Insights NOT found in DB!")


if __name__ == "__main__":
    asyncio.run(run_pipeline())
