from datetime import datetime
from pydantic import BaseModel, HttpUrl


class CompanyCreate(BaseModel):
    name: str
    website: str | None = None
    google_maps_url: str | None = None


class CompanyResponse(BaseModel):
    id: int
    name: str
    website: str | None = None
    google_maps_url: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CompanyList(BaseModel):
    companies: list[CompanyResponse]
    total: int
