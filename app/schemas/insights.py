from datetime import datetime
from pydantic import BaseModel


class CompanyInsightsResponse(BaseModel):
    id: int
    company_id: int
    strengths: list[str] | None = None
    weaknesses: list[str] | None = None
    feature_requests: list[str] | None = None
    overall_summary: str | None = None
    generated_at: datetime

    model_config = {"from_attributes": True}
