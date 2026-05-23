import logging
import json
from openai import AsyncOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"


async def generate_company_insights(
    company_name: str,
    reviews: list[dict],
    analyses: list[dict],
) -> dict:
    if not reviews:
        return {
            "strengths": [],
            "weaknesses": [],
            "feature_requests": [],
            "overall_summary": f"No reviews available for {company_name}.",
        }

    chunks = _chunk_reviews(reviews, analyses, chunk_size=50)
    chunk_summaries = []

    for i, chunk in enumerate(chunks):
        summary = await _summarize_chunk(company_name, chunk, i + 1, len(chunks))
        chunk_summaries.append(summary)

    combined = await _combine_summaries(company_name, chunk_summaries)
    return combined


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
        f"This is chunk {chunk_num}/{total_chunks} of Google Reviews for {company_name}, "
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
        f"Below are chunk-level summaries of Google Reviews for {company_name}, "
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
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=800,
        )
        content = response.choices[0].message.content.strip()
        content = content.removeprefix("```json").removesuffix("```").strip()
        return json.loads(content)
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
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=800,
        )
        content = response.choices[0].message.content.strip()
        content = content.removeprefix("```json").removesuffix("```").strip()
        return json.loads(content)
    except Exception as e:
        logger.error("Structured extraction failed: %s", e, exc_info=True)
        return {
            "strengths": [],
            "weaknesses": [],
            "feature_requests": [],
            "overall_summary": summary,
        }
