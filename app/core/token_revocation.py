import math
import time

from redis.asyncio import Redis

from app.core.configs import settings

# Redis-backed denylist for JWTs, with two kinds of entries:
#
# - A single revoked token, stored by its jti with a TTL equal to the
#   token's remaining lifetime, so the key removes itself once the token
#   would have expired anyway (logout, refresh token rotation).
# - A per-user "revoked before" timestamp: every token for that user
#   issued before it is rejected (password reset via the admin script,
#   scripts/reset_password.py). It lives as long as
#   the longest token lifetime, after which every older token has expired.
#
# These helpers let RedisError propagate: each caller decides whether a
# Redis outage fails open (access tokens) or closed (refresh, logout).

REVOKED_TOKEN_PREFIX = "revoked_token:"
TOKENS_REVOKED_BEFORE_PREFIX = "tokens_revoked_before:"


def revoked_token_key(jti: str) -> str:
    return f"{REVOKED_TOKEN_PREFIX}{jti}"


def tokens_revoked_before_key(subject: str) -> str:
    return f"{TOKENS_REVOKED_BEFORE_PREFIX}{subject}"


def remaining_ttl_seconds(payload: dict) -> int:
    return max(1, math.ceil(float(payload["exp"]) - time.time()))


def user_revocation_ttl_seconds() -> int:
    return settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60


async def revoke_token(redis: Redis, payload: dict) -> bool:
    """Atomically mark a token as revoked.

    Returns False if it was already revoked (e.g. a refresh token being
    reused), True otherwise. Legacy tokens without a jti can't be revoked
    and are reported as True: they stay valid until they expire.
    """
    jti = payload.get("jti")
    if jti is None:
        return True

    was_set = await redis.set(
        revoked_token_key(jti), "1", nx=True, ex=remaining_ttl_seconds(payload)
    )
    return bool(was_set)


async def revoke_tokens_issued_before(redis: Redis, subject: str, timestamp: float) -> None:
    await redis.set(
        tokens_revoked_before_key(subject), repr(timestamp), ex=user_revocation_ttl_seconds()
    )


async def is_token_revoked(redis: Redis, payload: dict) -> bool:
    jti = payload.get("jti")
    subject = payload.get("sub")

    keys = [tokens_revoked_before_key(subject)]
    if jti is not None:
        keys.append(revoked_token_key(jti))
    revoked_before, *revoked_jti = await redis.mget(keys)

    if revoked_jti and revoked_jti[0] is not None:
        return True

    if revoked_before is not None:
        # Tokens without an iat predate the revocation by definition.
        issued_at = payload.get("iat")
        if issued_at is None or float(issued_at) < float(revoked_before):
            return True

    return False
