from datetime import datetime
from pydantic import BaseModel


class ReviewAnalysisResponse(BaseModel):
    id: int
    review_id: int
    sentiment: str | None = None
    category: str | None = None
    short_summary: str | None = None
    analyzed_at: datetime

    model_config = {"from_attributes": True}
