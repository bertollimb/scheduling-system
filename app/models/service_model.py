import enum
from datetime import datetime, timezone

from sqlalchemy import String, Numeric, Boolean, DateTime, Enum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ServiceCategory(str, enum.Enum):
    HAIR_TREATMENT = "hair_treatment"
    COLOR_CUT = "color_cut"
    TREATMENT = "treatment"
    STRAIGHTENING = "straightening"


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[ServiceCategory] = mapped_column(Enum(ServiceCategory), nullable=False)
    price_from: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    duration_minutes: Mapped[int | None] = mapped_column(nullable=True)
    requires_evaluation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )