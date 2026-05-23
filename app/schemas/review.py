from datetime import datetime
from pydantic import BaseModel


class ReviewResponse(BaseModel):
    id: int
    company_id: int
    reviewer_name: str | None = None
    rating: int | None = None
    review_text: str | None = None
    review_date: str | None = None
    source: str
    scraped_at: datetime

    model_config = {"from_attributes": True}


class ReviewList(BaseModel):
    reviews: list[ReviewResponse]
    total: int
