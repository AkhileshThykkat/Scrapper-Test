import hashlib
import logging
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.review import Review

logger = logging.getLogger(__name__)


def generate_content_hash(source: str, reviewer_name: str | None, review_text: str | None, review_date: str | None) -> str:
    """
    Generate a deterministic SHA-256 fingerprint for a review.
    This is the primary dedup mechanism — survives across scrape runs,
    sources, and schema changes.
    """
    normalized = (
        f"{source}|"
        f"{(reviewer_name or '').strip().lower()}|"
        f"{(review_text or '').strip().lower()[:200]}|"
        f"{(review_date or '').strip()}"
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


async def is_duplicate_review(
    session: AsyncSession,
    company_id: int,
    review_data: dict,
    source: str = "google_maps",
) -> bool:
    """
    Check if a review already exists using content hash (primary)
    or fuzzy match (fallback for reviews without hash).
    """
    reviewer_name = review_data.get("reviewer_name", "")
    review_text = review_data.get("review_text", "")
    review_date = review_data.get("review_date", "")

    if not reviewer_name and not review_text:
        return False

    # Primary: content hash lookup (fast, indexed, scoped to company)
    content_hash = generate_content_hash(source, reviewer_name, review_text, review_date)
    result = await session.execute(
        select(Review.id).where(
            Review.company_id == company_id,
            Review.content_hash == content_hash,
        ).limit(1)
    )
    if result.scalar_one_or_none() is not None:
        return True

    # Fallback: fuzzy match for legacy reviews without content_hash
    text_prefix = review_text[:100] if review_text else ""
    conditions = [Review.company_id == company_id]
    if reviewer_name:
        conditions.append(Review.reviewer_name == reviewer_name)
    if text_prefix:
        conditions.append(Review.review_text.like(f"{text_prefix}%"))
    if review_date:
        conditions.append(Review.review_date == review_date)

    result = await session.execute(
        select(Review.id).where(and_(*conditions)).limit(1)
    )
    return result.scalar_one_or_none() is not None
