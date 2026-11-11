import asyncio
import time
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from jose import jwt
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core import token_revocation
from app.core.configs import settings
from app.core.deps import get_redis
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.main import app
from app.models.user_model import User


class UnavailableRedis:
    """Stand-in for a Redis outage: every command raises a connection error."""

    def __getattr__(self, name):
        async def fail(*args, **kwargs):
            raise RedisConnectionError("simulated Redis outage")

        return fail


def legacy_token(subject: str, token_type: str) -> str:
    # Tokens issued before this change carried no jti/iat claims.
    expire = datetime.now(timezone.utc) + timedelta(minutes=5)
    return jwt.encode(
        {"sub": subject, "exp": expire, "type": token_type},
        settings.JWT_SECRET,
        algorithm=settings.ALGORITHM,
    )


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_new_tokens_have_unique_jti(test_user: User):
    first = decode_token(create_access_token(test_user.email))
    second = decode_token(create_access_token(test_user.email))

    assert first["jti"] and second["jti"]
    assert first["jti"] != second["jti"]


@pytest.mark.asyncio
async def test_logout_invalidates_access_token(client: AsyncClient, test_user: User):
    access_token = create_access_token(test_user.email)

    assert (await client.get("/clients", headers=bearer(access_token))).status_code == 200

    logout_response = await client.post("/auth/logout", headers=bearer(access_token))
    assert logout_response.status_code == 204

    assert (await client.get("/clients", headers=bearer(access_token))).status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_refresh_token_when_sent(client: AsyncClient, test_user: User):
    access_token = create_access_token(test_user.email)
    refresh_token = create_refresh_token(test_user.email)

    logout_response = await client.post(
        "/auth/logout",
        json={"refresh_token": refresh_token},
        headers=bearer(access_token),
    )
    assert logout_response.status_code == 204

    refresh_response = await client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_response.status_code == 401


@pytest.mark.asyncio
async def test_logout_without_auth_fails(client: AsyncClient):
    response = await client.post("/auth/logout")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_cannot_be_used_twice(client: AsyncClient, test_user: User):
    refresh_token = create_refresh_token(test_user.email)

    first = await client.post("/auth/refresh", json={"refresh_token": refresh_token})
    second = await client.post("/auth/refresh", json={"refresh_token": refresh_token})

    assert first.status_code == 200
    assert second.status_code == 401

    # The rotated refresh token issued by the first call is still valid.
    rotated = await client.post(
        "/auth/refresh", json={"refresh_token": first.json()["refresh_token"]}
    )
    assert rotated.status_code == 200


@pytest.mark.asyncio
async def test_concurrent_refresh_only_one_succeeds(client: AsyncClient, test_user: User):
    refresh_token = create_refresh_token(test_user.email)

    responses = await asyncio.gather(
        client.post("/auth/refresh", json={"refresh_token": refresh_token}),
        client.post("/auth/refresh", json={"refresh_token": refresh_token}),
    )

    assert sorted(r.status_code for r in responses) == [200, 401]


@pytest.mark.asyncio
async def test_legacy_tokens_without_jti_still_work(client: AsyncClient, test_user: User):
    access_token = legacy_token(test_user.email, "access")
    refresh_token = legacy_token(test_user.email, "refresh")

    assert (await client.get("/clients", headers=bearer(access_token))).status_code == 200
    assert (await client.post("/auth/logout", headers=bearer(access_token))).status_code == 204

    refresh_response = await client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_response.status_code == 200


@pytest.mark.asyncio
async def test_revoked_key_expires_with_token(test_user: User):
    redis = await get_redis()
    expire = datetime.now(timezone.utc) + timedelta(seconds=2)
    payload = {"sub": test_user.email, "type": "access", "jti": "ttl-check", "exp": expire.timestamp()}
    key = token_revocation.revoked_token_key("ttl-check")

    assert await token_revocation.revoke_token(redis, payload) is True
    assert 0 < await redis.ttl(key) <= 2

    await asyncio.sleep(3)
    assert await redis.exists(key) == 0


@pytest.mark.asyncio
async def test_access_token_fails_open_when_redis_is_down(
    client: AsyncClient, test_user: User, monkeypatch
):
    access_token = create_access_token(test_user.email)
    monkeypatch.setitem(app.dependency_overrides, get_redis, lambda: UnavailableRedis())

    response = await client.get("/clients", headers=bearer(access_token))

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_refresh_fails_closed_when_redis_is_down(
    client: AsyncClient, test_user: User, monkeypatch
):
    refresh_token = create_refresh_token(test_user.email)
    monkeypatch.setitem(app.dependency_overrides, get_redis, lambda: UnavailableRedis())

    response = await client.post("/auth/refresh", json={"refresh_token": refresh_token})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_fails_closed_when_redis_is_down(
    client: AsyncClient, test_user: User, monkeypatch
):
    access_token = create_access_token(test_user.email)
    monkeypatch.setitem(app.dependency_overrides, get_redis, lambda: UnavailableRedis())

    response = await client.post("/auth/logout", headers=bearer(access_token))

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_tokens_issued_before_user_revocation_are_rejected(
    client: AsyncClient, test_user: User
):
    # scripts/reset_password.py calls revoke_tokens_issued_before after a
    # reset, so every session opened with the old password is dropped.
    old_access_token = create_access_token(test_user.email)
    old_refresh_token = create_refresh_token(test_user.email)
    legacy_access_token = legacy_token(test_user.email, "access")

    redis = await get_redis()
    await token_revocation.revoke_tokens_issued_before(redis, test_user.email, time.time())

    new_access_token = create_access_token(test_user.email)
    new_refresh_token = create_refresh_token(test_user.email)

    assert (await client.get("/clients", headers=bearer(old_access_token))).status_code == 401
    assert (await client.get("/clients", headers=bearer(legacy_access_token))).status_code == 401
    old_refresh = await client.post("/auth/refresh", json={"refresh_token": old_refresh_token})
    assert old_refresh.status_code == 401

    assert (await client.get("/clients", headers=bearer(new_access_token))).status_code == 200
    new_refresh = await client.post("/auth/refresh", json={"refresh_token": new_refresh_token})
    assert new_refresh.status_code == 200
