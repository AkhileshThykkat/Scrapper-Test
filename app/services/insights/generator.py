import logging
import json
from collections import Counter
from openai import AsyncOpenAI

from app.core.config import settings
from app.services.ai.analyzer import _extract_json

logger = logging.getLogger(__name__)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"

_SYSTEM_MSG = {"role": "system", "content": "You are a JSON-only response bot. Output raw JSON with no markdown formatting, no code blocks, no explanation. Just the JSON object."}


async def generate_company_insights(
    company_name: str,
    reviews: list[dict],
    analyses: list[dict],
) -> dict:
    """
    Generate comprehensive company insights including:
    - Standard strengths/weaknesses/feature_requests
    - Deep pain point analysis from negative reviews
    - Frequency and severity ranking of pain points
    """
    if not reviews:
        return {
            "strengths": [],
            "weaknesses": [],
            "feature_requests": [],
            "overall_summary": f"No reviews available for {company_name}.",
            "pain_points": [],
            "pain_point_summary": "",
            "negative_review_count": 0,
            "total_review_count": 0,
        }

    # Step 1: Aggregate pain points from individual review analyses
    aggregated_pain_points = _aggregate_pain_points(analyses)

    # Step 2: Filter negative/mixed reviews for deep analysis
    negative_reviews = _get_negative_reviews(reviews, analyses)

    # Step 3: Standard chunk-based analysis (all reviews)
    chunks = _chunk_reviews(reviews, analyses, chunk_size=50)
    chunk_summaries = []
    for i, chunk in enumerate(chunks):
        summary = await _summarize_chunk(company_name, chunk, i + 1, len(chunks))
        chunk_summaries.append(summary)

    combined = await _combine_summaries(company_name, chunk_summaries)

    # Step 4: Pain point deep-dive (negative reviews only)
    if negative_reviews:
        pain_point_analysis = await _analyze_pain_points(
            company_name, negative_reviews, aggregated_pain_points
        )
        combined["pain_points"] = pain_point_analysis.get("pain_points", [])
        combined["pain_point_summary"] = pain_point_analysis.get("pain_point_summary", "")
    else:
        combined["pain_points"] = aggregated_pain_points
        combined["pain_point_summary"] = f"No significant pain points identified for {company_name}."

    combined["negative_review_count"] = len(negative_reviews)
    combined["total_review_count"] = len(reviews)

    return combined


def _aggregate_pain_points(analyses: list[dict]) -> list[dict]:
    """Aggregate pain_points from individual review analyses into ranked list."""
    pain_counter: Counter = Counter()
    severity_totals: dict[str, float] = {}
    category_map: dict[str, str] = {}

    for a in analyses:
        points = a.get("pain_points", [])
        severity = a.get("severity", 0) or 0
        category = a.get("category", "General")

        if isinstance(points, list):
            for p in points:
                if isinstance(p, str) and p.strip():
                    normalized = p.strip().lower()
                    pain_counter[normalized] += 1
                    severity_totals[normalized] = severity_totals.get(normalized, 0) + severity
                    category_map[normalized] = category

    result = []
    for pain, count in pain_counter.most_common(20):
        result.append({
            "pain_point": pain,
            "frequency": count,
            "severity_avg": round(severity_totals[pain] / count, 1) if count > 0 else 0,
            "category": category_map.get(pain, "General"),
        })

    return result


def _get_negative_reviews(reviews: list[dict], analyses: list[dict]) -> list[dict]:
    """Extract reviews with negative or mixed sentiment for deep analysis."""
    analysis_map = {a["review_id"]: a for a in analyses}
    negative = []

    for r in reviews:
        a = analysis_map.get(r["id"], {})
        sentiment = a.get("sentiment", "neutral")
        if sentiment in ("negative", "mixed"):
            negative.append({
                "review_text": r.get("review_text", ""),
                "rating": r.get("rating"),
                "category": a.get("category", "unknown"),
                "pain_points": a.get("pain_points", []),
                "severity": a.get("severity", 0),
            })

    return negative


async def _analyze_pain_points(
    company_name: str,
    negative_reviews: list[dict],
    aggregated_pain_points: list[dict],
) -> dict:
    """Deep-dive LLM analysis of negative reviews to identify actionable pain points."""
    client = AsyncOpenAI(api_key=settings.groq_api_key, base_url=GROQ_BASE_URL)

    # Limit to top 50 negative reviews to fit context window
    sample = negative_reviews[:50]
    reviews_text = json.dumps(sample, indent=2)
    aggregated_text = json.dumps(aggregated_pain_points[:15], indent=2)

    prompt = (
        f"You are a competitive intelligence analyst. Below are negative/mixed reviews "
        f"for {company_name}, a WhatsApp CRM/marketing service, along with pre-aggregated "
        f"pain point frequencies.\n\n"
        f"Negative reviews ({len(sample)}/{len(negative_reviews)} total):\n{reviews_text}\n\n"
        f"Pre-aggregated pain points:\n{aggregated_text}\n\n"
        f"Analyze these and provide a JSON response with:\n"
        f'- "pain_points": ranked list of objects, each with:\n'
        f'    - "pain_point": concise, actionable description\n'
        f'    - "frequency": how many reviews mention this (int)\n'
        f'    - "severity_avg": average severity 1-5 (float)\n'
        f'    - "category": which product area this affects\n'
        f'    - "example_reviews": 2-3 short quotes from actual reviews\n'
        f'- "pain_point_summary": 3-5 sentence executive summary of the biggest '
        f'customer pain points and what they reveal about the product.\n\n'
        f"Rank by impact (frequency × severity). Merge similar complaints.\n"
        f"Respond with ONLY valid JSON, no markdown."
    )

    try:
        response = await client.chat.completions.create(
            model=settings.groq_model,
            messages=[_SYSTEM_MSG, {"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=3000,
        )
        content = response.choices[0].message.content or ""
        return _extract_json(content)
    except Exception as e:
        logger.error("Pain point analysis failed: %s", e, exc_info=True)
        return {
            "pain_points": aggregated_pain_points,
            "pain_point_summary": f"Automated pain point analysis failed. "
                                  f"{len(negative_reviews)} negative reviews found for {company_name}.",
        }


def _chunk_reviews(
    reviews: list[dict],
    analyses: list[dict],
    chunk_size: int = 50,
) -> list[list[dict]]:
    analysis_map = {a["review_id"]: a for a in analyses}
    combined = []

    for r in reviews:
        a = analysis_map.get(r["id"], {})
        combined.append({
            "review_text": r.get("review_text", ""),
            "sentiment": a.get("sentiment", "unknown"),
            "category": a.get("category", "unknown"),
            "rating": r.get("rating"),
        })

    return [combined[i : i + chunk_size] for i in range(0, len(combined), chunk_size)]


async def _summarize_chunk(
    company_name: str,
    chunk: list[dict],
    chunk_num: int,
    total_chunks: int,
) -> str:
    client = AsyncOpenAI(api_key=settings.groq_api_key, base_url=GROQ_BASE_URL)

    reviews_text = json.dumps(chunk, indent=2)

    prompt = (
        f"This is chunk {chunk_num}/{total_chunks} of reviews for {company_name}, "
        f"a WhatsApp CRM service.\n\n"
        f"Reviews with sentiment and category:\n{reviews_text}\n\n"
        f"Analyze this chunk and provide:\n"
        f"1. Common themes\n"
        f"2. Key strengths mentioned\n"
        f"3. Key complaints/weaknesses\n"
        f"4. Feature requests or improvement suggestions\n"
        f"5. Overall sentiment of this chunk\n\n"
        f"Keep it concise (2-3 paragraphs)."
    )

    try:
        response = await client.chat.completions.create(
            model=settings.groq_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=500,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error("Chunk summarization failed: %s", e, exc_info=True)
        return f"Chunk {chunk_num}: summary unavailable."


async def _combine_summaries(company_name: str, chunk_summaries: list[str]) -> dict:
    if len(chunk_summaries) == 1:
        return await _extract_structured(company_name, chunk_summaries[0])

    client = AsyncOpenAI(api_key=settings.groq_api_key, base_url=GROQ_BASE_URL)

    combined_text = "\n\n---\n\n".join(
        f"Chunk {i+1}:\n{s}" for i, s in enumerate(chunk_summaries)
    )

    prompt = (
        f"Below are chunk-level summaries of reviews for {company_name}, "
        f"a WhatsApp CRM service.\n\n"
        f"{combined_text}\n\n"
        f"Combine these into a final structured analysis. "
        f"Respond with ONLY valid JSON with these fields:\n"
        f'- "strengths": list of top strengths (strings)\n'
        f'- "weaknesses": list of top complaints (strings)\n'
        f'- "feature_requests": list of most requested improvements (strings)\n'
        f'- "overall_summary": 3-4 sentence overall summary\n\n'
        f"Respond with ONLY valid JSON, no markdown."
    )

    try:
        response = await client.chat.completions.create(
            model=settings.groq_model,
            messages=[_SYSTEM_MSG, {"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=800,
        )
        content = response.choices[0].message.content or ""
        return _extract_json(content)
    except Exception as e:
        logger.error("Combined summarization failed: %s", e, exc_info=True)
        return {
            "strengths": [],
            "weaknesses": [],
            "feature_requests": [],
            "overall_summary": f"Analysis generated from {len(chunk_summaries)} chunks for {company_name}.",
        }


async def _extract_structured(company_name: str, summary: str) -> dict:
    client = AsyncOpenAI(api_key=settings.groq_api_key, base_url=GROQ_BASE_URL)
    prompt = (
        f"Extract structured insights from this review analysis for {company_name}, "
        f"a WhatsApp CRM service.\n\n"
        f"Analysis:\n{summary}\n\n"
        f"Respond with ONLY valid JSON:\n"
        f'- "strengths": list of top strengths (strings)\n'
        f'- "weaknesses": list of top complaints (strings)\n'
        f'- "feature_requests": list of most requested improvements (strings)\n'
        f'- "overall_summary": 3-4 sentence overall summary'
    )

    try:
        response = await client.chat.completions.create(
            model=settings.groq_model,
            messages=[_SYSTEM_MSG, {"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=800,
        )
        content = response.choices[0].message.content or ""
        return _extract_json(content)
    except Exception as e:
        logger.error("Structured extraction failed: %s", e, exc_info=True)
        return {
            "strengths": [],
            "weaknesses": [],
            "feature_requests": [],
            "overall_summary": summary,
        }
