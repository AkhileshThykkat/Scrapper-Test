from datetime import datetime
from typing import Any
from pydantic import BaseModel


class CompanyInsightsResponse(BaseModel):
    id: int
    company_id: int
    strengths: list[str] | None = None
    weaknesses: list[str] | None = None
    feature_requests: list[str] | None = None
    overall_summary: str | None = None
    pain_points: list[Any] | None = None
    pain_point_summary: str | None = None
    negative_review_count: int | None = 0
    total_review_count: int | None = 0
    generated_at: datetime

    model_config = {"from_attributes": True}
