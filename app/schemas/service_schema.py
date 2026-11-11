from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.service_model import ServiceCategory


class ServiceBase(BaseModel):
    name: str
    category: ServiceCategory
    price_from: Decimal = Field(gt=0)
    duration_minutes: int | None = None
    requires_evaluation: bool = False


class ServiceCreate(ServiceBase):
    pass


class ServiceUpdate(BaseModel):
    name: str | None = None
    category: ServiceCategory | None = None
    price_from: Decimal | None = Field(default=None, gt=0)
    duration_minutes: int | None = None
    requires_evaluation: bool | None = None

    @field_validator("name", "category", "price_from", "requires_evaluation")
    @classmethod
    def reject_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("field cannot be null")
        return value


class ServiceOut(ServiceBase):
    id: int

    model_config = ConfigDict(from_attributes=True)