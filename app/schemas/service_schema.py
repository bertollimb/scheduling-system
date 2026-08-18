from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

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


class ServiceOut(ServiceBase):
    id: int

    model_config = ConfigDict(from_attributes=True)