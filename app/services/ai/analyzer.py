import json
import logging
import re
from openai import AsyncOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"

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


def _extract_json(text: str) -> dict:
    """
    Robustly extract JSON from LLM responses that may be wrapped in
    markdown code blocks, have extra whitespace, or contain preamble text.
    """
    if not text or not text.strip():
        raise ValueError("Empty response from LLM")

    # Strategy 1: Try direct parse (clean response)
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # Strategy 2: Extract from ```json ... ``` or ``` ... ``` blocks
    code_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if code_block:
        try:
            return json.loads(code_block.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Strategy 3: Find the first { ... } or [ ... ] block in the text
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    # Strategy 4: Try stripping common prefixes the model might add
    for prefix in ["Here is the JSON:", "Here's the JSON:", "JSON:", "Response:"]:
        if prefix.lower() in text.lower():
            after = text[text.lower().index(prefix.lower()) + len(prefix):]
            try:
                return json.loads(after.strip())
            except json.JSONDecodeError:
                pass

    raise ValueError(f"Could not extract JSON from LLM response: {text[:200]}")


async def analyze_review_text(review_text: str) -> dict:
    """
    Analyze a single review to extract sentiment, category, summary,
    and — for negative/mixed reviews — specific pain points.
    """
    client = AsyncOpenAI(api_key=settings.groq_api_key, base_url=GROQ_BASE_URL)

    prompt = (
        f"Analyze the following review for a WhatsApp CRM/marketing service.\n\n"
        f"Review: \"{review_text}\"\n\n"
        f"Provide a JSON response with exactly these fields:\n"
        f"- sentiment: one of {SENTIMENTS}\n"
        f"- category: choose the single best category from {CATEGORIES}\n"
        f"- short_summary: a 10-15 word summary of the review\n"
        f"- pain_points: a list of specific pain points or complaints mentioned "
        f"(empty list if sentiment is positive). Each pain point should be a short, "
        f"actionable phrase like \"slow customer support response\" or "
        f"\"pricing too high for small businesses\"\n"
        f"- severity: for negative/mixed reviews, rate severity 1-5 (5=critical). "
        f"Set to 0 for positive/neutral reviews.\n\n"
        f"Respond with ONLY valid JSON, no markdown or explanation."
    )

    try:
        response = await client.chat.completions.create(
            model=settings.groq_model,
            messages=[
                {"role": "system", "content": "You are a JSON-only response bot. Output raw JSON with no markdown formatting, no code blocks, no explanation. Just the JSON object."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=400,
        )
        content = response.choices[0].message.content or ""
        content = content.strip()

        logger.debug("Raw LLM response: %s", content[:300])

        result = _extract_json(content)

        if result.get("sentiment") not in SENTIMENTS:
            result["sentiment"] = "neutral"
        if result.get("category") not in CATEGORIES:
            result["category"] = "General"
        if not isinstance(result.get("pain_points"), list):
            result["pain_points"] = []
        if not isinstance(result.get("severity"), (int, float)):
            result["severity"] = 0

        return result

    except Exception as e:
        logger.error("Groq analysis failed for review: %s", e, exc_info=True)
        return {
            "sentiment": "neutral",
            "category": "General",
            "short_summary": review_text[:100],
            "pain_points": [],
            "severity": 0,
        }
