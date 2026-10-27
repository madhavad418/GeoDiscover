from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class PoiComparisonReview(Base):
    __tablename__ = "poi_comparison_reviews"
    __table_args__ = (
        UniqueConstraint("dataset_id", "provider", "record_key"),
        Index("ix_poi_comparison_reviews_dataset_status", "dataset_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    dataset_id: Mapped[UUID] = mapped_column(ForeignKey("customer_datasets.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(16))
    record_key: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(12), default="pending", server_default="pending")
    note: Mapped[str] = mapped_column(Text, default="", server_default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
