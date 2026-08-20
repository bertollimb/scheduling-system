import pytest
from httpx import AsyncClient

from app.core.security import create_access_token, create_refresh_token
from app.models.user_model import User


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, test_user: User):
    response = await client.post(
        "/auth/login",
        data={"username": test_user.email, "password": "TestPassword123"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password_fails(client: AsyncClient, test_user: User):
    response = await client.post(
        "/auth/login",
        data={"username": test_user.email, "password": "WrongPassword"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_email_fails(client: AsyncClient):
    response = await client.post(
        "/auth/login",
        data={"username": "nobody@example.com", "password": "AnyPassword123"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_email_is_case_insensitive(client: AsyncClient, test_user: User):
    response = await client.post(
        "/auth/login",
        data={"username": test_user.email.upper(), "password": "TestPassword123"},
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_login_email_ignores_surrounding_whitespace(
    client: AsyncClient, test_user: User
):
    response = await client.post(
        "/auth/login",
        data={"username": f"  {test_user.email}  ", "password": "TestPassword123"},
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_refresh_with_valid_token_succeeds(client: AsyncClient, test_user: User):
    refresh_token = create_refresh_token(test_user.email)

    response = await client.post("/auth/refresh", json={"refresh_token": refresh_token})

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


@pytest.mark.asyncio
async def test_refresh_with_malformed_token_fails(client: AsyncClient):
    response = await client.post(
        "/auth/refresh", json={"refresh_token": "not.a.valid.token"}
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_with_access_token_fails(client: AsyncClient, test_user: User):
    # An access token has type="access", not "refresh" - the refresh
    # endpoint must reject it even though it's otherwise a valid, signed
    # token for this user.
    access_token = create_access_token(test_user.email)

    response = await client.post("/auth/refresh", json={"refresh_token": access_token})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_rate_limiting_blocks_after_five_failures(
    client: AsyncClient, test_user: User
):
    for _ in range(5):
        response = await client.post(
            "/auth/login",
            data={"username": test_user.email, "password": "WrongPassword"},
        )
        assert response.status_code == 401

    blocked_response = await client.post(
        "/auth/login",
        data={"username": test_user.email, "password": "WrongPassword"},
    )
    assert blocked_response.status_code == 429


@pytest.mark.asyncio
async def test_login_rate_limit_does_not_block_correct_password(
    client: AsyncClient, test_user: User
):
    # Only 4 failures - one below the threshold - then a correct login
    # should still succeed and reset the counter.
    for _ in range(4):
        await client.post(
            "/auth/login",
            data={"username": test_user.email, "password": "WrongPassword"},
        )

    response = await client.post(
        "/auth/login",
        data={"username": test_user.email, "password": "TestPassword123"},
    )
    assert response.status_code == 200