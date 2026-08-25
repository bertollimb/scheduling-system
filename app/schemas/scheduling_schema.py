from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.scheduling_model import AppointmentType, AppointmentStatus

LISBON_TZ = ZoneInfo("Europe/Lisbon")


class SchedulingCreate(BaseModel):
    client_id: int
    service_id: int
    start_time: datetime
    type: AppointmentType
    evaluation_id: int | None = None
    duration_minutes: int | None = Field(default=None, gt=0)

    @field_validator("start_time")
    @classmethod
    def normalize_and_validate_start_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            value = value.replace(tzinfo=LISBON_TZ)
        else:
            value = value.astimezone(LISBON_TZ)

        if value < datetime.now(LISBON_TZ):
            raise ValueError("start_time cannot be in the past")

        return value

    @model_validator(mode="after")
    def validate_evaluation_link(self) -> "SchedulingCreate":
        if self.type == AppointmentType.EVALUATION and self.evaluation_id is not None:
            raise ValueError("evaluation_id must not be set when creating an evaluation")
        if self.type == AppointmentType.EVALUATION and self.duration_minutes is not None:
            raise ValueError("duration_minutes must not be set when creating an evaluation")
        return self


class CompleteEvaluationRequest(BaseModel):
    estimated_duration_minutes: int = Field(
        ge=300,
        le=480,
        description="Estimated duration in minutes (5 to 8 hours)",
    )


class SchedulingOut(BaseModel):
    id: int
    client_id: int
    service_id: int
    start_time: datetime
    end_time: datetime
    type: AppointmentType
    status: AppointmentStatus
    evaluation_id: int | None
    estimated_duration_minutes: int | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)