"""Saved HERE vs Google/Grab comparisons: the New / Update / Delete / Matched / Review lists per AOI.

Saved at the user's request (2026-10-27) so the results and their metrics stay available to the team.
"""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .platform import Json


class ProviderComparison(Base):
    __tablename__ = "provider_comparisons"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    aoi: Mapped[str] = mapped_column(String(80), index=True)
    dataset_id: Mapped[UUID | None] = mapped_column(ForeignKey("customer_datasets.id", ondelete="SET NULL"))
    dataset_filename: Mapped[str] = mapped_column(String(255), default="")
    extract_filename: Mapped[str] = mapped_column(String(255), default="")
    source_filename: Mapped[str] = mapped_column(String(255), default="")  # uploaded comparison workbook, if any
    stats: Mapped[dict] = mapped_column(Json, default=dict)
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProviderComparisonRow(Base):
    __tablename__ = "provider_comparison_rows"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    comparison_id: Mapped[UUID] = mapped_column(ForeignKey("provider_comparisons.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(16))      # new | update | delete | matched | review
    position: Mapped[int] = mapped_column(Integer)      # order within its list
    name: Mapped[str] = mapped_column(String(500), default="")
    here_placeid: Mapped[str] = mapped_column(String(120), default="")
    delete_basis: Mapped[str] = mapped_column(String(60), default="")
    search_text: Mapped[str] = mapped_column(String(2000), default="")  # lower-cased name, IDs, address for search
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    data: Mapped[dict] = mapped_column(Json, default=dict)  # every column of the row, as in the Excel sheet

    __table_args__ = (Index("ix_provider_rows_comparison_kind", "comparison_id", "kind", "position"),)
