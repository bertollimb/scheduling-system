from datetime import datetime

from pydantic import BaseModel, EmailStr, ConfigDict, Field


class ClientBase(BaseModel):
    first_name: str = Field(min_length=1)
    last_name: str = Field(min_length=1)
    phone: str = Field(min_length=1)
    email: EmailStr | None = None


class ClientCreate(ClientBase):
    pass


class ClientUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1)
    last_name: str | None = Field(default=None, min_length=1)
    phone: str | None = Field(default=None, min_length=1)
    email: EmailStr | None = None


class ClientOut(ClientBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)