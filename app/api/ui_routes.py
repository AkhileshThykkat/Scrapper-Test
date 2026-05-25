from fastapi import APIRouter, Depends, Request, Form, Form
from fastapi.responses import HTMLResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.company import Company
from app.models.review import Review
from app.models.company_insights import CompanyInsight

router = APIRouter()

@router.get("/companies/ui-list", response_class=HTMLResponse)
async def list_companies_ui(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(
            Company.id,
            Company.name,
            Company.website,
            Company.google_maps_url,
            func.count(Review.id).label("review_count")
        )
        .outerjoin(Review, Review.company_id == Company.id)
        .group_by(Company.id)
        .order_by(Company.id.desc())
    )
    companies = result.all()

    if not companies:
        return """
        <div class="bg-white rounded-2xl shadow-sm border border-slate-200 p-8 text-center text-slate-500">
            No companies added yet. Use the form on the left to add one.
        </div>
        """

    html = ""
    for c in companies:
        html += f"""
        <div class="bg-white rounded-2xl shadow-sm border border-slate-200 p-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4 transition-all hover:shadow-md">
            <div>
                <h3 class="text-lg font-bold text-slate-900">{c.name}</h3>
                <div class="flex items-center gap-3 mt-2 text-sm text-slate-500">
                    <span class="flex items-center gap-1">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"></path></svg>
                        {c.review_count} Reviews
                    </span>
                    {f'<a href="{c.website}" target="_blank" class="hover:text-brand-600 truncate max-w-[150px]">{c.website}</a>' if c.website else ''}
                </div>
            </div>
            <div class="flex flex-wrap gap-2">
                <button hx-post="/api/v1/companies/{c.id}/scrape" hx-swap="none" onclick="alert('Scraping started in background!')" class="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm font-medium rounded-lg transition-colors flex items-center gap-1">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"></path></svg>
                    Scrape
                </button>
                <button hx-post="/api/v1/companies/{c.id}/analyze" hx-swap="none" onclick="alert('Analysis started in background!')" class="px-3 py-1.5 bg-brand-50 hover:bg-brand-100 text-brand-700 text-sm font-medium rounded-lg transition-colors flex items-center gap-1">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
                    Analyze
                </button>
                <button hx-get="/api/v1/companies/{c.id}/ui-insights" hx-target="#company-detail-modal" class="px-3 py-1.5 bg-slate-800 hover:bg-slate-900 text-white text-sm font-medium rounded-lg transition-colors">
                    Insights
                </button>
            </div>
        </div>
        """
    return html

@router.post("/companies/ui-create", response_class=HTMLResponse)
async def create_company_ui(
    name: str = Form(...),
    website: str | None = Form(None),
    google_maps_url: str | None = Form(None),
    session: AsyncSession = Depends(get_session)
):
    company = Company(
        name=name,
        website=website,
        google_maps_url=google_maps_url,
    )
    session.add(company)
    await session.commit()
    await session.refresh(company)
    
    html = f"""
    <div class="bg-white rounded-2xl shadow-sm border border-slate-200 p-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4 transition-all hover:shadow-md fade-in">
        <div>
            <h3 class="text-lg font-bold text-slate-900">{company.name}</h3>
            <div class="flex items-center gap-3 mt-2 text-sm text-slate-500">
                <span class="flex items-center gap-1">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"></path></svg>
                    0 Reviews
                </span>
                {f'<a href="{company.website}" target="_blank" class="hover:text-brand-600 truncate max-w-[150px]">{company.website}</a>' if company.website else ''}
            </div>
        </div>
        <div class="flex flex-wrap gap-2">
            <button hx-post="/api/v1/companies/{company.id}/scrape" hx-swap="none" onclick="alert('Scraping started in background!')" class="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm font-medium rounded-lg transition-colors flex items-center gap-1">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"></path></svg>
                Scrape
            </button>
            <button hx-post="/api/v1/companies/{company.id}/analyze" hx-swap="none" onclick="alert('Analysis started in background!')" class="px-3 py-1.5 bg-brand-50 hover:bg-brand-100 text-brand-700 text-sm font-medium rounded-lg transition-colors flex items-center gap-1">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
                Analyze
            </button>
            <button hx-get="/api/v1/companies/{company.id}/ui-insights" hx-target="#company-detail-modal" class="px-3 py-1.5 bg-slate-800 hover:bg-slate-900 text-white text-sm font-medium rounded-lg transition-colors">
                Insights
            </button>
        </div>
    </div>
    """
    return html


@router.get("/companies/{company_id}/ui-insights", response_class=HTMLResponse)
async def company_insights_ui(company_id: int, session: AsyncSession = Depends(get_session)):
    # Fetch company
    c_result = await session.execute(select(Company).where(Company.id == company_id))
    company = c_result.scalar_one_or_none()
    
    if not company:
        return "<div class='p-4 text-red-500'>Company not found</div>"

    # Fetch insights
    i_result = await session.execute(select(CompanyInsight).where(CompanyInsight.company_id == company_id))
    insights = i_result.scalar_one_or_none()

    if not insights:
        return f"""
        <div class="fixed inset-0 z-50 flex items-center justify-center p-4">
            <div class="bg-white rounded-2xl shadow-xl border border-slate-200 w-full max-w-2xl max-h-[90vh] overflow-y-auto relative p-6">
                <button onclick="closeModal()" class="absolute top-4 right-4 text-slate-400 hover:text-slate-600 bg-slate-100 rounded-full p-1 transition-colors">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
                </button>
                <h2 class="text-2xl font-bold text-slate-900 mb-4">{company.name} Insights</h2>
                <div class="p-4 bg-amber-50 text-amber-800 rounded-xl border border-amber-200">
                    No insights available yet. Run a scrape and analyze first.
                </div>
            </div>
        </div>
        """

    pain_points_html = ""
    for i, pp in enumerate(insights.pain_points or []):
        if isinstance(pp, dict):
            pain_points_html += f"""
            <div class="mb-4 p-4 bg-slate-50 rounded-xl border border-slate-100">
                <div class="flex justify-between items-start mb-2">
                    <h4 class="font-semibold text-slate-800">{i+1}. {pp.get("pain_point")}</h4>
                    <span class="bg-red-100 text-red-800 text-xs font-semibold px-2.5 py-0.5 rounded">Severity: {pp.get("severity_avg", "?")}/5</span>
                </div>
                <p class="text-sm text-slate-600 mb-2"><span class="font-medium text-slate-700">Category:</span> {pp.get("category", "?")} | <span class="font-medium text-slate-700">Mentions:</span> {pp.get("frequency", "?")}</p>
                <div class="text-xs text-slate-500 italic space-y-1 mt-2 border-l-2 border-slate-300 pl-3">
            """
            for ex in pp.get("example_reviews", [])[:2]:
                pain_points_html += f'<p>"{ex}"</p>'
            pain_points_html += "</div></div>"
        else:
            pain_points_html += f'<div class="mb-2 p-3 bg-slate-50 rounded-lg text-sm text-slate-700">{i+1}. {pp}</div>'

    html = f"""
    <div class="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6">
        <div class="bg-white rounded-2xl shadow-xl border border-slate-200 w-full max-w-4xl max-h-[90vh] flex flex-col relative fade-in">
            <div class="p-6 border-b border-slate-100 flex justify-between items-center sticky top-0 bg-white/95 backdrop-blur z-10 rounded-t-2xl">
                <div>
                    <h2 class="text-2xl font-bold text-slate-900">{company.name} Intelligence Report</h2>
                    <p class="text-sm text-slate-500 mt-1">Based on {insights.total_review_count} reviews ({insights.negative_review_count} negative)</p>
                </div>
                <button onclick="closeModal()" class="text-slate-400 hover:text-slate-600 bg-slate-100 rounded-full p-2 transition-colors focus:outline-none">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
                </button>
            </div>
            
            <div class="p-6 overflow-y-auto flex-grow space-y-8">
                
                <!-- Executive Summary -->
                <section>
                    <h3 class="text-lg font-bold text-slate-900 mb-3 flex items-center gap-2">
                        <svg class="w-5 h-5 text-brand-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path></svg>
                        Executive Summary
                    </h3>
                    <div class="p-5 bg-brand-50 text-brand-900 rounded-xl leading-relaxed text-sm border border-brand-100">
                        {insights.overall_summary or "No summary available."}
                    </div>
                </section>

                <!-- Strengths & Weaknesses Grid -->
                <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div class="bg-green-50/50 p-5 rounded-xl border border-green-100">
                        <h3 class="font-bold text-green-800 mb-4 flex items-center gap-2">
                            <svg class="w-5 h-5 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 10h4.764a2 2 0 011.789 2.894l-3.5 7A2 2 0 0115.263 21h-4.017c-.163 0-.326-.02-.485-.06L7 20m7-10V5a2 2 0 00-2-2h-.095c-.5 0-.905.405-.905.905 0 .714-.211 1.412-.608 2.006L7 11v9m7-10h-2M7 20H5a2 2 0 01-2-2v-6a2 2 0 012-2h2.5"></path></svg>
                            Key Strengths
                        </h3>
                        <ul class="space-y-2">
                            {''.join(f'<li class="text-sm text-green-900 flex items-start gap-2"><span class="text-green-500 mt-0.5">•</span> <span>{s}</span></li>' for s in insights.strengths or [])}
                        </ul>
                    </div>
                    <div class="bg-red-50/50 p-5 rounded-xl border border-red-100">
                        <h3 class="font-bold text-red-800 mb-4 flex items-center gap-2">
                            <svg class="w-5 h-5 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 14H5.236a2 2 0 01-1.789-2.894l3.5-7A2 2 0 018.736 3h4.018a2 2 0 01.485.06l3.76.94m-7 10v5a2 2 0 002 2h.096c.5 0 .905-.405.905-.904 0-.715.211-1.413.608-2.008L17 13V4m-7 10h2m5-10h2a2 2 0 012 2v6a2 2 0 01-2 2h-2.5"></path></svg>
                            Key Weaknesses
                        </h3>
                        <ul class="space-y-2">
                            {''.join(f'<li class="text-sm text-red-900 flex items-start gap-2"><span class="text-red-500 mt-0.5">•</span> <span>{w}</span></li>' for w in insights.weaknesses or [])}
                        </ul>
                    </div>
                </div>

                <!-- Deep Dive Pain Points -->
                <section>
                    <h3 class="text-lg font-bold text-slate-900 mb-2 flex items-center gap-2">
                        <svg class="w-5 h-5 text-rose-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
                        Deep-Dive Pain Points
                    </h3>
                    <p class="text-sm text-slate-500 mb-4">{insights.pain_point_summary}</p>
                    
                    <div class="mt-4">
                        {pain_points_html}
                    </div>
                </section>

                <!-- Feature Requests -->
                <section>
                    <h3 class="text-lg font-bold text-slate-900 mb-3 flex items-center gap-2">
                        <svg class="w-5 h-5 text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
                        Top Feature Requests
                    </h3>
                    <div class="flex flex-wrap gap-2">
                        {''.join(f'<span class="px-3 py-1 bg-amber-50 text-amber-700 border border-amber-200 rounded-full text-sm font-medium">{f}</span>' for f in insights.feature_requests or [])}
                    </div>
                </section>
                
            </div>
        </div>
    </div>
    """
    return html
