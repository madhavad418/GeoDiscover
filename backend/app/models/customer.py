from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import UserDefinedType

from ..db import Base


class PointGeometry(UserDefinedType):
    cache_ok = True

    def get_col_spec(self, **kw):
        return "geometry(Point,4326)"


class CustomerDataset(Base):
    __tablename__ = "customer_datasets"
    __table_args__ = (UniqueConstraint("aoi", "sha256"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    filename: Mapped[str] = mapped_column(Text)
    customer: Mapped[str] = mapped_column(String(100), default="HERE")
    aoi: Mapped[str] = mapped_column(String(100))
    country: Mapped[str] = mapped_column(String(3))
    sha256: Mapped[str] = mapped_column(String(64))
    row_count: Mapped[int] = mapped_column(Integer)
    columns: Mapped[list] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CustomerPoi(Base):
    __tablename__ = "customer_pois"
    __table_args__ = (
        UniqueConstraint("dataset_id", "place_id"),
        Index("ix_customer_pois_display_point", "display_point", postgresql_using="gist"),
        Index("ix_customer_pois_routing_point", "routing_point", postgresql_using="gist"),
        Index("ix_customer_pois_dataset_category", "dataset_id", "category_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[UUID] = mapped_column(ForeignKey("customer_datasets.id", ondelete="CASCADE"))
    place_id: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    category_code: Mapped[str | None] = mapped_column(Text)
    category_name: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str] = mapped_column(String(3))
    address: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    routing_latitude: Mapped[float | None] = mapped_column(Float)
    routing_longitude: Mapped[float | None] = mapped_column(Float)
    display_point = mapped_column(PointGeometry(), nullable=False)
    routing_point = mapped_column(PointGeometry())
    raw: Mapped[dict] = mapped_column(JSONB)
