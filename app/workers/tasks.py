import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import async_session_factory
from app.models.company import Company
from app.models.review import Review
from app.models.review_analysis import ReviewAnalysis
from app.models.company_insights import CompanyInsight
from app.services.scraping.google_reviews import scrape_google_reviews
from app.services.ai.analyzer import analyze_review_text, CATEGORIES, SENTIMENTS
from app.services.embeddings.generator import generate_embedding
from app.services.insights.generator import generate_company_insights
from app.utils.dedup import is_duplicate_review, generate_content_hash
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, max_retries=3, queue="scrape_queue")
def scrape_reviews_task(self, company_id: int):
    logger.info("Starting scrape task for company_id=%d", company_id)
    return _run_async(_scrape_reviews(self, company_id))


async def _scrape_reviews(self, company_id: int):
    async with async_session_factory() as session:
        result = await session.execute(select(Company).where(Company.id == company_id))
        company = result.scalar_one_or_none()

        if not company:
            logger.error("Company %d not found", company_id)
            return {"error": "Company not found"}

        if not company.google_maps_url:
            logger.error("Company %d has no Google Maps URL", company_id)
            return {"error": "No Google Maps URL configured"}

        raw_reviews = await scrape_google_reviews(company.name, company.google_maps_url)

        stored_count = 0
        for r in raw_reviews:
            if not r.get("review_text"):
                continue

            if await is_duplicate_review(session, company_id, r):
                continue

            content_hash = generate_content_hash(
                "google_maps",
                r.get("reviewer_name"),
                r.get("review_text"),
                r.get("review_date"),
            )

            review = Review(
                company_id=company_id,
                reviewer_name=r.get("reviewer_name"),
                rating=r.get("rating"),
                review_text=r.get("review_text"),
                review_date=r.get("review_date"),
                source="google_maps",
                content_hash=content_hash,
                is_processed=False,
            )
            session.add(review)
            stored_count += 1

        await session.commit()
        logger.info("Stored %d reviews for company %s", stored_count, company.name)

        if stored_count > 0:
            analyze_reviews_task.delay(company_id)

        return {"company_id": company_id, "reviews_scraped": len(raw_reviews), "reviews_stored": stored_count}


@celery_app.task(bind=True, max_retries=3, queue="analysis_queue")
def analyze_reviews_task(self, company_id: int):
    logger.info("Starting analysis task for company_id=%d", company_id)
    return _run_async(_analyze_reviews(self, company_id))


async def _analyze_reviews(self, company_id: int):
    async with async_session_factory() as session:
        # Find unprocessed reviews (using is_processed flag instead of subquery)
        result = await session.execute(
            select(Review).where(
                Review.company_id == company_id,
                Review.is_processed == False,
            )
        )
        unanalyzed_reviews = result.scalars().all()

        if not unanalyzed_reviews:
            logger.info("No unanalyzed reviews for company %d", company_id)
            return {"company_id": company_id, "analyzed": 0}

        analyzed_count = 0
        for review in unanalyzed_reviews:
            if not review.review_text:
                review.is_processed = True
                continue

            analysis = await analyze_review_text(review.review_text)

            try:
                embedding = generate_embedding(review.review_text)
            except Exception as e:
                logger.error("Embedding failed for review %d: %s", review.id, e)
                embedding = None

            review_analysis = ReviewAnalysis(
                review_id=review.id,
                sentiment=analysis.get("sentiment"),
                category=analysis.get("category"),
                short_summary=analysis.get("short_summary"),
                pain_points=analysis.get("pain_points", []),
                severity=analysis.get("severity", 0),
                embedding_vector=embedding,
            )
            session.add(review_analysis)
            review.is_processed = True
            analyzed_count += 1

        await session.commit()
        logger.info("Analyzed %d reviews for company %d", analyzed_count, company_id)

        await _generate_insights_for_company(session, company_id)

        return {"company_id": company_id, "analyzed": analyzed_count}


async def _generate_insights_for_company(session: AsyncSession, company_id: int):
    result = await session.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if not company:
        return

    reviews_result = await session.execute(
        select(Review).where(Review.company_id == company_id)
    )
    reviews = reviews_result.scalars().all()

    analyses_result = await session.execute(
        select(ReviewAnalysis).where(
            ReviewAnalysis.review_id.in_([r.id for r in reviews])
        )
    )
    analyses = analyses_result.scalars().all()

    if not analyses:
        return

    reviews_data = [
        {"id": r.id, "review_text": r.review_text, "rating": r.rating}
        for r in reviews
    ]
    analyses_data = [
        {
            "review_id": a.review_id,
            "sentiment": a.sentiment,
            "category": a.category,
            "pain_points": a.pain_points or [],
            "severity": a.severity or 0,
        }
        for a in analyses
    ]

    insights = await generate_company_insights(company.name, reviews_data, analyses_data)

    existing = await session.execute(
        select(CompanyInsight).where(CompanyInsight.company_id == company_id)
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
            company_id=company_id,
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
    logger.info("Insights generated for company %d", company_id)
