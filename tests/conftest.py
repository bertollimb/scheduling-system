import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.core.configs import settings
from app.core.security import hash_password
from app.db.base import Base
from app.core.deps import get_db, get_redis
from app.main import app
from app.models.user_model import User

TEST_DB_URL = str(settings.TEST_DB_URL)
TEST_USER_EMAIL = "test@example.com"

test_engine = create_async_engine(TEST_DB_URL)
TestSessionLocal = async_sessionmaker(bind=test_engine, expire_on_commit=False)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_database():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    connection = await test_engine.connect()
    outer_transaction = await connection.begin()

    session = TestSessionLocal(bind=connection)

    nested = await connection.begin_nested()

    @event.listens_for(session.sync_session, "after_transaction_end")
    def restart_savepoint(sync_session, transaction):
        nonlocal nested
        if not nested.is_active:
            nested = connection.sync_connection.begin_nested()

    yield session

    await session.close()
    await outer_transaction.rollback()
    await connection.close()


@pytest_asyncio.fixture(autouse=True)
async def cleanup_redis() -> AsyncGenerator[None, None]:
    redis = await get_redis()
    attempts_key = f"login_attempts:{TEST_USER_EMAIL}"

    await redis.delete(attempts_key)
    yield
    await redis.delete(attempts_key)


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    user = User(
        email=TEST_USER_EMAIL,
        hashed_password=hash_password("TestPassword123"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient, test_user: User) -> dict[str, str]:
    response = await client.post(
        "/auth/login",
        data={"username": test_user.email, "password": "TestPassword123"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}