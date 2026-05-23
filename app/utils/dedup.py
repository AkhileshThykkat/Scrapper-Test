import logging
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.review import Review

logger = logging.getLogger(__name__)


async def is_duplicate_review(
    session: AsyncSession,
    company_id: int,
    review_data: dict,
) -> bool:
    reviewer_name = review_data.get("reviewer_name", "")
    review_text = review_data.get("review_text", "")[:100] if review_data.get("review_text") else ""
    review_date = review_data.get("review_date", "")

    if not reviewer_name and not review_text:
        return False

    conditions = [Review.company_id == company_id]
    if reviewer_name:
        conditions.append(Review.reviewer_name == reviewer_name)
    if review_text:
        conditions.append(Review.review_text.like(f"{review_text}%"))
    if review_date:
        conditions.append(Review.review_date == review_date)

    result = await session.execute(
        select(Review.id).where(and_(*conditions)).limit(1)
    )
    return result.scalar_one_or_none() is not None
