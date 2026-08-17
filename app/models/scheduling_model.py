import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, DateTime, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.client_model import Client
    from app.models.service_model import Service


class AppointmentType(str, enum.Enum):
    EVALUATION = "evaluation"
    PROCEDURE = "procedure"


class AppointmentStatus(str, enum.Enum):
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class Scheduling(Base):
    __tablename__ = "schedulings"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id"), nullable=False, index=True
    )
    service_id: Mapped[int] = mapped_column(
        ForeignKey("services.id"), nullable=False, index=True
    )

    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    end_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    type: Mapped[AppointmentType] = mapped_column(Enum(AppointmentType), nullable=False)
    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(AppointmentStatus), default=AppointmentStatus.CONFIRMED, nullable=False
    )

    evaluation_id: Mapped[int | None] = mapped_column(
        ForeignKey("schedulings.id"), nullable=True
    )
    estimated_duration_minutes: Mapped[int | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    client: Mapped["Client"] = relationship()
    service: Mapped["Service"] = relationship()
    evaluation: Mapped["Scheduling | None"] = relationship(remote_side=[id])