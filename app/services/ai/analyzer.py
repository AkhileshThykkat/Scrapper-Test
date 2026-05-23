import logging
from openai import AsyncOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

CATEGORIES = [
    "Pricing",
    "Customer Support",
    "Ease of Use",
    "Reliability",
    "Features",
    "Performance",
    "UI/UX",
    "Automation",
    "Onboarding",
    "WhatsApp API Issues",
]

SENTIMENTS = ["positive", "negative", "mixed", "neutral"]


async def analyze_review_text(review_text: str) -> dict:
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    prompt = (
        f"Analyze the following Google Review for a WhatsApp CRM service.\n\n"
        f"Review: \"{review_text}\"\n\n"
        f"Provide a JSON response with exactly these fields:\n"
        f"- sentiment: one of {SENTIMENTS}\n"
        f"- category: choose the single best category from {CATEGORIES}\n"
        f"- short_summary: a 10-15 word summary of the review\n\n"
        f"Respond with ONLY valid JSON, no markdown or explanation."
    )

    try:
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=200,
        )
        content = response.choices[0].message.content.strip()

        import json

        content = content.removeprefix("```json").removesuffix("```").strip()
        result = json.loads(content)

        if result.get("sentiment") not in SENTIMENTS:
            result["sentiment"] = "neutral"
        if result.get("category") not in CATEGORIES:
            result["category"] = "General"

        return result

    except Exception as e:
        logger.error("OpenAI analysis failed for review: %s", e, exc_info=True)
        return {"sentiment": "neutral", "category": "General", "short_summary": review_text[:100]}
