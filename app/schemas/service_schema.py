from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.service_model import ServiceCategory


class ServiceBase(BaseModel):
    name: str
    category: ServiceCategory
    price_from: Decimal
    duration_minutes: int | None = None
    requires_evaluation: bool = False


class ServiceCreate(ServiceBase):
    pass


class ServiceUpdate(BaseModel):
    name: str | None = None
    category: ServiceCategory | None = None
    price_from: Decimal | None = None
    duration_minutes: int | None = None
    requires_evaluation: bool | None = None


class ServiceOut(ServiceBase):
    id: int

    model_config = ConfigDict(from_attributes=True)