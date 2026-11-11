from datetime import datetime, timedelta, timezone
from uuid import uuid4

from jose import jwt, JWTError
from passlib.context import CryptContext

from app.core.configs import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

PASSWORD_MIN_LENGTH = 8
# bcrypt only uses the first 72 bytes of a password and silently ignores
# the rest, so longer passwords are rejected instead of truncated.
PASSWORD_MAX_BYTES = 72


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def validate_password_strength(password: str) -> str:
    if len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"Password must be at least {PASSWORD_MIN_LENGTH} characters long")
    if len(password.encode("utf-8")) > PASSWORD_MAX_BYTES:
        raise ValueError(f"Password must be at most {PASSWORD_MAX_BYTES} bytes long")
    if not any(char.isalpha() for char in password):
        raise ValueError("Password must contain at least one letter")
    if not any(char.isdigit() for char in password):
        raise ValueError("Password must contain at least one digit")
    return password


def _create_token(subject: str, token_type: str, expires_delta: timedelta) -> str:
    now = datetime.now(timezone.utc)
    to_encode = {
        "sub": subject,
        "exp": now + expires_delta,
        "type": token_type,
        "jti": uuid4().hex,
        # Sub-second precision, so a password change can invalidate every
        # token issued before it without also rejecting the new pair it
        # issues in the same second.
        "iat": now.timestamp(),
    }
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.ALGORITHM)


def create_access_token(subject: str) -> str:
    return _create_token(
        subject, "access", timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )


def create_refresh_token(subject: str) -> str:
    return _create_token(
        subject, "refresh", timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None
