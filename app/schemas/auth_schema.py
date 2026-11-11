from pydantic import BaseModel, field_validator, model_validator

from app.core.security import validate_password_strength


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def check_strength(cls, value: str) -> str:
        return validate_password_strength(value)

    @model_validator(mode="after")
    def check_password_changes(self) -> "ChangePasswordRequest":
        if self.new_password == self.current_password:
            raise ValueError("new_password must be different from current_password")
        return self