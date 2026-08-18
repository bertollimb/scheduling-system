from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, get_redis
from app.core.security import (
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.models.user_model import User
from app.schemas.auth_schema import Token, RefreshRequest

router = APIRouter(prefix="/auth", tags=["auth"])

MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 300  # 5 minutes


@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> Token:
    normalized_email = form_data.username.strip().lower()
    attempts_key = f"login_attempts:{normalized_email}"

    # Rate limiting is a defense-in-depth measure, not the primary auth
    # mechanism. If Redis is unavailable, login must still work against
    # the database - we fail open here rather than locking everyone out.
    try:
        current_attempts = await redis.get(attempts_key)
        if current_attempts is not None and int(current_attempts) >= MAX_LOGIN_ATTEMPTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many failed login attempts. Please try again later.",
            )
    except RedisError:
        current_attempts = None

    result = await db.execute(select(User).where(User.email == normalized_email))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(form_data.password, user.hashed_password):
        try:
            pipe = redis.pipeline()
            pipe.incr(attempts_key)
            pipe.expire(attempts_key, LOGIN_LOCKOUT_SECONDS)
            await pipe.execute()
        except RedisError:
            pass

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    try:
        await redis.delete(attempts_key)
    except RedisError:
        pass

    return Token(
        access_token=create_access_token(user.email),
        refresh_token=create_refresh_token(user.email),
    )


@router.post("/refresh", response_model=Token)
async def refresh(data: RefreshRequest, db: AsyncSession = Depends(get_db)) -> Token:
    invalid_token_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
    )

    payload = decode_token(data.refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise invalid_token_exception

    email = payload.get("sub")
    if email is None:
        raise invalid_token_exception

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        raise invalid_token_exception

    return Token(
        access_token=create_access_token(user.email),
        refresh_token=create_refresh_token(user.email),
    )