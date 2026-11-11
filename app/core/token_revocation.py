import math
import time

from redis.asyncio import Redis

# Redis-backed denylist for JWTs. Each revoked token is stored by its jti
# with a TTL equal to the token's remaining lifetime, so the key removes
# itself once the token would have expired anyway.
#
# These helpers let RedisError propagate: each caller decides whether a
# Redis outage fails open (access tokens) or closed (refresh, logout).

REVOKED_TOKEN_PREFIX = "revoked_token:"


def revoked_token_key(jti: str) -> str:
    return f"{REVOKED_TOKEN_PREFIX}{jti}"


def remaining_ttl_seconds(payload: dict) -> int:
    return max(1, math.ceil(float(payload["exp"]) - time.time()))


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


async def is_token_revoked(redis: Redis, payload: dict) -> bool:
    jti = payload.get("jti")
    if jti is None:
        return False
    return await redis.exists(revoked_token_key(jti)) == 1
