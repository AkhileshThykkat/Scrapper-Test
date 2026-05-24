"""
Test the sentiment analyzer + pain point extraction pipeline
using sample reviews from reviewsample.txt.

No database, no Celery, no Playwright — just the LLM analysis.
"""
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

from app.services.ai.analyzer import analyze_review_text
from app.services.insights.generator import generate_company_insights


def load_reviews(filepath: str) -> list[str]:
    """Load reviews from file, split by '---' delimiter."""
    text = Path(filepath).read_text()
    reviews = [r.strip() for r in text.split("---") if r.strip()]
    return reviews


async def test_individual_analysis(reviews: list[str]) -> list[dict]:
    """Analyze each review individually and collect results."""
    results = []

    for i, review_text in enumerate(reviews):
        logger.info("=" * 70)
        logger.info("REVIEW %d/%d", i + 1, len(reviews))
        logger.info("-" * 70)
        logger.info("Text: %s", review_text[:120] + ("..." if len(review_text) > 120 else ""))

        start = time.time()
        analysis = await analyze_review_text(review_text)
        elapsed = time.time() - start

        logger.info("Sentiment:   %s", analysis.get("sentiment"))
        logger.info("Category:    %s", analysis.get("category"))
        logger.info("Summary:     %s", analysis.get("short_summary"))
        logger.info("Severity:    %s", analysis.get("severity"))
        logger.info("Pain Points: %s", analysis.get("pain_points"))
        logger.info("Time:        %.2fs", elapsed)

        results.append({
            "id": i + 1,
            "review_text": review_text,
            "rating": _guess_rating(analysis.get("sentiment", "neutral")),
            **analysis,
        })

        # Small delay to respect rate limits
        await asyncio.sleep(0.5)

    return results


async def test_insights_generation(reviews_data: list[dict], analyses_data: list[dict]):
    """Test the full insights pipeline including pain point deep-dive."""
    logger.info("\n" + "=" * 70)
    logger.info("GENERATING COMPANY INSIGHTS + PAIN POINT ANALYSIS")
    logger.info("=" * 70)

    start = time.time()
    insights = await generate_company_insights(
        company_name="TestCRM (Hypothetical WhatsApp CRM)",
        reviews=reviews_data,
        analyses=analyses_data,
    )
    elapsed = time.time() - start

    logger.info("\n" + "=" * 70)
    logger.info("INSIGHTS RESULTS (generated in %.2fs)", elapsed)
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

    logger.info("\n📊 OVERALL SUMMARY:")
    logger.info("  %s", insights.get("overall_summary", "N/A"))

    logger.info("\n📊 TOTAL REVIEWS: %d", insights.get("total_review_count", 0))
    logger.info("📊 NEGATIVE REVIEWS: %d", insights.get("negative_review_count", 0))

    logger.info("\n" + "=" * 70)
    logger.info("🔴 PAIN POINT ANALYSIS")
    logger.info("=" * 70)

    pain_points = insights.get("pain_points", [])
    if pain_points:
        for i, pp in enumerate(pain_points):
            if isinstance(pp, dict):
                logger.info(
                    "\n  %d. %s",
                    i + 1,
                    pp.get("pain_point", "Unknown"),
                )
                logger.info("     Frequency: %s mentions", pp.get("frequency", "?"))
                logger.info("     Severity:  %s/5", pp.get("severity_avg", "?"))
                logger.info("     Category:  %s", pp.get("category", "?"))
                examples = pp.get("example_reviews", [])
                if examples:
                    for ex in examples[:2]:
                        logger.info('     Quote: "%s"', str(ex)[:100])
            else:
                logger.info("  %d. %s", i + 1, pp)
    else:
        logger.info("  No pain points extracted")

    logger.info("\n📊 PAIN POINT SUMMARY:")
    logger.info("  %s", insights.get("pain_point_summary", "N/A"))

    return insights


def _guess_rating(sentiment: str) -> int:
    """Map sentiment to a plausible star rating for test data."""
    return {"positive": 5, "negative": 1, "mixed": 3, "neutral": 3}.get(sentiment, 3)


async def main():
    reviews_file = sys.argv[1] if len(sys.argv) > 1 else "reviewsample.txt"

    logger.info("Loading reviews from %s...", reviews_file)
    raw_reviews = load_reviews(reviews_file)
    logger.info("Loaded %d reviews\n", len(raw_reviews))

    # Step 1: Individual review analysis
    analyses = await test_individual_analysis(raw_reviews)

    # Summary stats
    sentiments = [a["sentiment"] for a in analyses]
    logger.info("\n" + "=" * 70)
    logger.info("ANALYSIS SUMMARY")
    logger.info("=" * 70)
    logger.info("Total reviews:  %d", len(analyses))
    logger.info("Positive:       %d", sentiments.count("positive"))
    logger.info("Negative:       %d", sentiments.count("negative"))
    logger.info("Mixed:          %d", sentiments.count("mixed"))
    logger.info("Neutral:        %d", sentiments.count("neutral"))

    all_pain_points = []
    for a in analyses:
        all_pain_points.extend(a.get("pain_points", []))
    logger.info("Total pain points extracted: %d", len(all_pain_points))

    # Step 2: Company-level insights + pain point deep-dive
    reviews_data = [
        {"id": a["id"], "review_text": a["review_text"], "rating": a["rating"]}
        for a in analyses
    ]
    analyses_data = [
        {
            "review_id": a["id"],
            "sentiment": a["sentiment"],
            "category": a["category"],
            "pain_points": a.get("pain_points", []),
            "severity": a.get("severity", 0),
        }
        for a in analyses
    ]

    insights = await test_insights_generation(reviews_data, analyses_data)

    # Save full results to JSON for inspection
    output = {
        "individual_analyses": analyses,
        "company_insights": insights,
    }
    output_path = Path("test_analysis_results.json")
    output_path.write_text(json.dumps(output, indent=2, default=str))
    logger.info("\n📁 Full results saved to %s", output_path)


if __name__ == "__main__":
    asyncio.run(main())
