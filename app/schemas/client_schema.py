from datetime import datetime

from pydantic import BaseModel, EmailStr, ConfigDict, Field, field_validator


def _blank_to_none(value: str | None) -> str | None:
    if isinstance(value, str) and not value.strip():
        return None
    return value


class ClientBase(BaseModel):
    first_name: str = Field(min_length=1)
    last_name: str = Field(min_length=1)
    phone: str | None = Field(default=None, min_length=1)
    email: EmailStr | None = None

    @field_validator("phone", mode="before")
    @classmethod
    def normalize_blank_phone(cls, value: str | None) -> str | None:
        return _blank_to_none(value)


class ClientCreate(ClientBase):
    pass


class ClientUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1)
    last_name: str | None = Field(default=None, min_length=1)
    phone: str | None = Field(default=None, min_length=1)
    email: EmailStr | None = None

    @field_validator("phone", mode="before")
    @classmethod
    def normalize_blank_phone(cls, value: str | None) -> str | None:
        return _blank_to_none(value)


class ClientOut(ClientBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)