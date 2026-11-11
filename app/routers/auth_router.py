from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, get_redis, get_current_user, oauth2_scheme
from app.core.security import (
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.core.token_revocation import revoke_token
from app.models.user_model import User
from app.schemas.auth_schema import Token, RefreshRequest, LogoutRequest

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
async def refresh(
    data: RefreshRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> Token:
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

    # Refresh token rotation: the presented token is atomically marked as
    # used (SET NX) before a new pair is issued, so it can only be
    # exchanged once - of two concurrent requests with the same token,
    # exactly one succeeds. A token revoked by logout fails the same way.
    # This check fails closed: refresh tokens are long-lived, so if Redis
    # is unavailable the refresh is refused (login still works).
    try:
        if not await revoke_token(redis, payload):
            raise invalid_token_exception
    except RedisError:
        raise invalid_token_exception

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        raise invalid_token_exception

    return Token(
        access_token=create_access_token(user.email),
        refresh_token=create_refresh_token(user.email),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    data: LogoutRequest | None = None,
    token: str = Depends(oauth2_scheme),
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> None:
    payloads = [decode_token(token)]

    # The refresh token is optional. It is only revoked if it is a valid
    # refresh token for the same user; anything else has nothing to revoke.
    if data is not None and data.refresh_token is not None:
        refresh_payload = decode_token(data.refresh_token)
        if (
            refresh_payload is not None
            and refresh_payload.get("type") == "refresh"
            and refresh_payload.get("sub") == user.email
        ):
            payloads.append(refresh_payload)

    # Logout fails closed: if Redis is unavailable the tokens can't be
    # revoked, so the API reports it instead of pretending it worked.
    try:
        for payload in payloads:
            await revoke_token(redis, payload)
    except RedisError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Logout is temporarily unavailable, please try again",
        )
