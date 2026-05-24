from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Text, ForeignKey, func, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class CompanyInsight(Base):
    __tablename__ = "company_insights"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id"), nullable=False, unique=True)
    strengths: Mapped[list | None] = mapped_column(JSON)
    weaknesses: Mapped[list | None] = mapped_column(JSON)
    feature_requests: Mapped[list | None] = mapped_column(JSON)
    overall_summary: Mapped[str | None] = mapped_column(Text)

    # Pain point analytics — the core competitive intelligence output
    pain_points: Mapped[list | None] = mapped_column(JSON)
    # Format: [{"pain_point": "...", "frequency": 12, "severity_avg": 3.8,
    #           "category": "Customer Support", "example_reviews": ["...", "..."]}]

    pain_point_summary: Mapped[str | None] = mapped_column(Text)
    # AI-generated narrative summary of the top pain points

    negative_review_count: Mapped[int | None] = mapped_column(Integer, default=0)
    total_review_count: Mapped[int | None] = mapped_column(Integer, default=0)

    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    company = relationship("Company", back_populates="insights")
