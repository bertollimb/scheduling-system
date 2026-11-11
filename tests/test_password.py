import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import validate_password_strength, verify_password
from app.models.user_model import User
from app.services import auth_service

CURRENT_PASSWORD = "TestPassword123"
NEW_PASSWORD = "NewPassword456"


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
