from datetime import datetime

from pydantic import BaseModel, EmailStr, ConfigDict


class ClientBase(BaseModel):
    first_name: str
    last_name: str
    phone: str
    email: EmailStr | None = None


class ClientCreate(ClientBase):
    pass


class ClientUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    email: EmailStr | None = None


class ClientOut(ClientBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)