import pytest
from httpx import AsyncClient
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_redis
from app.core.security import create_refresh_token, validate_password_strength, verify_password
from app.main import app
from app.models.user_model import User
from app.services import auth_service

CURRENT_PASSWORD = "TestPassword123"
NEW_PASSWORD = "NewPassword456"


class UnavailableRedis:
    def __getattr__(self, name):
        async def fail(*args, **kwargs):
            raise RedisConnectionError("simulated Redis outage")

        return fail


async def change_password(client: AsyncClient, headers: dict[str, str], current: str, new: str):
    return await client.post(
        "/auth/change-password",
        json={"current_password": current, "new_password": new},
        headers=headers,
    )


async def login(client: AsyncClient, email: str, password: str):
    return await client.post("/auth/login", data={"username": email, "password": password})


@pytest.mark.asyncio
async def test_change_password_succeeds(
    client: AsyncClient, test_user: User, auth_headers: dict[str, str]
):
    response = await change_password(client, auth_headers, CURRENT_PASSWORD, NEW_PASSWORD)

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data

    assert (await login(client, test_user.email, NEW_PASSWORD)).status_code == 200
    assert (await login(client, test_user.email, CURRENT_PASSWORD)).status_code == 401


@pytest.mark.asyncio
async def test_change_password_with_wrong_current_password_fails(
    client: AsyncClient, test_user: User, auth_headers: dict[str, str]
):
    response = await change_password(client, auth_headers, "WrongPassword1", NEW_PASSWORD)

    assert response.status_code == 403
    assert (await login(client, test_user.email, CURRENT_PASSWORD)).status_code == 200


@pytest.mark.asyncio
async def test_change_password_without_auth_fails(client: AsyncClient, test_user: User):
    response = await change_password(client, {}, CURRENT_PASSWORD, NEW_PASSWORD)

    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "new_password",
    ["Short1", "OnlyLetters", "1234567890", "A1" + "a" * 71, CURRENT_PASSWORD],
    ids=["too-short", "no-digit", "no-letter", "over-72-bytes", "same-as-current"],
)
async def test_change_password_with_weak_new_password_fails(
    client: AsyncClient, test_user: User, auth_headers: dict[str, str], new_password: str
):
    response = await change_password(client, auth_headers, CURRENT_PASSWORD, new_password)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_change_password_invalidates_previous_tokens(
    client: AsyncClient, test_user: User, auth_headers: dict[str, str]
):
    old_refresh_token = create_refresh_token(test_user.email)

    response = await change_password(client, auth_headers, CURRENT_PASSWORD, NEW_PASSWORD)
    assert response.status_code == 200
    new_tokens = response.json()

    assert (await client.get("/clients", headers=auth_headers)).status_code == 401
    old_refresh = await client.post("/auth/refresh", json={"refresh_token": old_refresh_token})
    assert old_refresh.status_code == 401

    new_headers = {"Authorization": f"Bearer {new_tokens['access_token']}"}
    assert (await client.get("/clients", headers=new_headers)).status_code == 200
    new_refresh = await client.post(
        "/auth/refresh", json={"refresh_token": new_tokens["refresh_token"]}
    )
    assert new_refresh.status_code == 200


@pytest.mark.asyncio
async def test_change_password_still_works_when_redis_is_down(
    client: AsyncClient, test_user: User, auth_headers: dict[str, str], monkeypatch
):
    monkeypatch.setitem(app.dependency_overrides, get_redis, lambda: UnavailableRedis())

    response = await change_password(client, auth_headers, CURRENT_PASSWORD, NEW_PASSWORD)

    assert response.status_code == 200
    monkeypatch.delitem(app.dependency_overrides, get_redis)
    assert (await login(client, test_user.email, NEW_PASSWORD)).status_code == 200


# ---- Service-layer tests: the reset function used by scripts/reset_password.py ----

@pytest.mark.asyncio
async def test_reset_password_updates_hash(db_session: AsyncSession, test_user: User):
    updated = await auth_service.reset_password(
        db_session, f"  {test_user.email.upper()} ", NEW_PASSWORD
    )

    assert updated is True
    await db_session.refresh(test_user)
    assert test_user.hashed_password != NEW_PASSWORD
    assert verify_password(NEW_PASSWORD, test_user.hashed_password)
    assert not verify_password(CURRENT_PASSWORD, test_user.hashed_password)


@pytest.mark.asyncio
async def test_reset_password_for_unknown_email_returns_false(db_session: AsyncSession):
    assert await auth_service.reset_password(db_session, "nobody@example.com", NEW_PASSWORD) is False


@pytest.mark.asyncio
async def test_reset_password_rejects_weak_password(db_session: AsyncSession, test_user: User):
    with pytest.raises(ValueError):
        await auth_service.reset_password(db_session, test_user.email, "weak")

    await db_session.refresh(test_user)
    assert verify_password(CURRENT_PASSWORD, test_user.hashed_password)


def test_validate_password_strength_accepts_valid_password():
    assert validate_password_strength(NEW_PASSWORD) == NEW_PASSWORD
