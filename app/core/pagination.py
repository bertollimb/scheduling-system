from typing import Any

from fastapi import Query, Response
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

# Generous default so a small salon's full dataset still fits in a single
# page: the frontend expects a plain list and shows every record at once.
DEFAULT_LIMIT = 1000
MAX_LIMIT = 5000
TOTAL_COUNT_HEADER = "X-Total-Count"


class PaginationParams:
    def __init__(
        self,
        skip: int = Query(0, ge=0),
        limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    ) -> None:
        self.skip = skip
        self.limit = limit


async def paginate(
    db: AsyncSession, query: Select, pagination: PaginationParams, response: Response
) -> list[Any]:
    """Run a list query with skip/limit and set the X-Total-Count header.

    The total is counted from the same (filtered) query, before skip/limit.
    The query must already have a deterministic ORDER BY.
    """
    total = await db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    response.headers[TOTAL_COUNT_HEADER] = str(total)

    result = await db.execute(query.offset(pagination.skip).limit(pagination.limit))
    return list(result.scalars().all())
