from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, validate_password_strength
from app.models.user_model import User


async def set_user_password(db: AsyncSession, user: User, new_password: str) -> None:
    validate_password_strength(new_password)
    user.hashed_password = hash_password(new_password)
    await db.commit()


async def reset_password(db: AsyncSession, email: str, new_password: str) -> bool:
    """Set a new password for the user with this email, bypassing the
    current one. Used by the admin script. Returns False if no such user."""
    normalized_email = email.strip().lower()
    result = await db.execute(select(User).where(User.email == normalized_email))
    user = result.scalar_one_or_none()
    if user is None:
        return False

    await set_user_password(db, user, new_password)
    return True
