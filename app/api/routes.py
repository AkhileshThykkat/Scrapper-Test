from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.company import Company
from app.models.review import Review
from app.models.review_analysis import ReviewAnalysis
from app.models.company_insights import CompanyInsight
from app.schemas.company import CompanyCreate, CompanyResponse, CompanyList
from app.schemas.review import ReviewResponse, ReviewList
from app.schemas.analysis import ReviewAnalysisResponse
from app.schemas.insights import CompanyInsightsResponse
from app.workers.tasks import scrape_reviews_task, analyze_reviews_task

router = APIRouter()


@router.post("/companies", response_model=CompanyResponse, status_code=201)
async def create_company(
    data: CompanyCreate,
    session: AsyncSession = Depends(get_session),
):
    company = Company(
        name=data.name,
        website=data.website,
        google_maps_url=data.google_maps_url,
    )
    session.add(company)
    await session.flush()
    await session.refresh(company)
    return company


@router.get("/companies", response_model=CompanyList)
async def list_companies(
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Company).order_by(Company.name))
    companies = result.scalars().all()
    return CompanyList(
        companies=[CompanyResponse.model_validate(c) for c in companies],
        total=len(companies),
    )


@router.post("/companies/{company_id}/scrape")
async def scrape_company_reviews(
    company_id: int,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    task = scrape_reviews_task.delay(company_id)
    return {"status": "queued", "task_id": task.id, "company_id": company_id}


@router.get("/companies/{company_id}/reviews", response_model=ReviewList)
async def list_reviews(
    company_id: int,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    reviews_result = await session.execute(
        select(Review).where(Review.company_id == company_id).order_by(Review.scraped_at.desc())
    )
    reviews = reviews_result.scalars().all()
    return ReviewList(
        reviews=[ReviewResponse.model_validate(r) for r in reviews],
        total=len(reviews),
    )


@router.post("/companies/{company_id}/analyze")
async def analyze_company_reviews(
    company_id: int,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    task = analyze_reviews_task.delay(company_id)
    return {"status": "queued", "task_id": task.id, "company_id": company_id}


@router.get("/companies/{company_id}/insights", response_model=CompanyInsightsResponse)
async def get_company_insights(
    company_id: int,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(CompanyInsight).where(CompanyInsight.company_id == company_id)
    )
    insight = result.scalar_one_or_none()
    if not insight:
        raise HTTPException(
            status_code=404,
            detail="Insights not yet generated. Trigger analysis first.",
        )
    return insight
