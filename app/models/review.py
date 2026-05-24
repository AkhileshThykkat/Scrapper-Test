from datetime import datetime
from sqlalchemy import String, Integer, Boolean, DateTime, Text, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id"), nullable=False)
    reviewer_name: Mapped[str | None] = mapped_column(String(255))
    rating: Mapped[int | None] = mapped_column(Integer)
    review_text: Mapped[str | None] = mapped_column(Text)
    review_date: Mapped[str | None] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(64), default="google_maps")
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Dedup: SHA-256 fingerprint of source+reviewer+text+date for reliable duplicate detection
    content_hash: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)

    # Processing tracking: has this review been analyzed?
    is_processed: Mapped[bool] = mapped_column(Boolean, default=False)

    company = relationship("Company", back_populates="reviews")
    analysis = relationship("ReviewAnalysis", back_populates="review", cascade="all, delete-orphan", uselist=False)
