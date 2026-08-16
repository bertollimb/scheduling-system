from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator

from app.models.scheduling_model import AppointmentType, AppointmentStatus


class SchedulingCreate(BaseModel):
    client_id: int
    service_id: int
    start_time: datetime
    type: AppointmentType
    evaluation_id: int | None = None

    @model_validator(mode="after")
    def validate_evaluation_link(self) -> "SchedulingCreate":
        if self.type == AppointmentType.EVALUATION and self.evaluation_id is not None:
            raise ValueError("evaluation_id must not be set when creating an evaluation")
        return self


class CompleteEvaluationRequest(BaseModel):
    estimated_duration_minutes: int


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