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
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    company = relationship("Company", back_populates="insights")
