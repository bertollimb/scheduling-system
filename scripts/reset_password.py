"""Reset a user's password from the command line.

Usage (from the repository root):

    python -m scripts.reset_password <email>

The database is the one configured in DB_URL (environment or .env). The
new password is read with getpass and is never printed, logged, or passed
as a command-line argument. Tokens issued before the reset are revoked
(best effort: if Redis is unavailable they stay valid until they expire).
"""
import argparse
import asyncio
import getpass
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from redis.exceptions import RedisError  # noqa: E402

from app.core.configs import settings  # noqa: E402
from app.core.deps import close_redis, get_redis  # noqa: E402
from app.core.security import validate_password_strength  # noqa: E402
from app.core.token_revocation import revoke_tokens_issued_before  # noqa: E402
from app.db.session import async_session_maker, engine  # noqa: E402
from app.services.auth_service import reset_password  # noqa: E402


def prompt_new_password() -> str:
    password = getpass.getpass("New password: ")
    if password != getpass.getpass("Repeat new password: "):
        raise ValueError("Passwords do not match")
    return validate_password_strength(password)


async def run(email: str, new_password: str) -> int:
    changed_at = time.time()
    try:
        async with async_session_maker() as session:
            updated = await reset_password(session, email, new_password)
    finally:
        await engine.dispose()

    if not updated:
        print(f"No user found with email {email!r}. Nothing was changed.")
        return 1
    print("Password updated.")

    try:
        redis = await get_redis()
        await revoke_tokens_issued_before(redis, email.strip().lower(), changed_at)
        print("Tokens issued before the reset were revoked.")
    except RedisError:
        print("Warning: Redis is unavailable; existing tokens stay valid until they expire.")
    finally:
        await close_redis()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset a user's password.")
    parser.add_argument("email", help="email of the account to reset")
    args = parser.parse_args()

    db_host = settings.DB_URL.hosts()[0]["host"]
    db_name = (settings.DB_URL.path or "").lstrip("/")
    print(f"Target database: {db_name} on host {db_host}")
    if input("Type 'yes' to continue: ").strip().lower() != "yes":
        print("Aborted. Nothing was changed.")
        return 1

    try:
        new_password = prompt_new_password()
    except ValueError as e:
        print(f"Error: {e}. Nothing was changed.")
        return 1

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(run(args.email, new_password))


if __name__ == "__main__":
    sys.exit(main())
