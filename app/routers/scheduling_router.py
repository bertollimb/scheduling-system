from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from redis.exceptions import LockError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, get_current_user, get_redis
from app.core.exceptions import NotFoundError
from app.models.scheduling_model import Scheduling
from app.schemas.scheduling_schema import (
    SchedulingCreate,
    SchedulingOut,
    CompleteEvaluationRequest,
)
from app.services import scheduling_service

router = APIRouter(
    prefix="/schedulings",
    tags=["schedulings"],
    dependencies=[Depends(get_current_user)],
)

# Lock TTL with a wide safety margin over the expected operation time
# (a few DB queries + one insert), to avoid the lock expiring mid-operation
# during a transient slowdown.
LOCK_TIMEOUT_SECONDS = 30
LOCK_BLOCKING_TIMEOUT_SECONDS = 10
SCHEDULING_LOCK_KEY = "lock:scheduling:create"
LISBON_TZ = ZoneInfo("Europe/Lisbon")


@router.post("", response_model=SchedulingOut, status_code=status.HTTP_201_CREATED)
async def create_scheduling(
    data: SchedulingCreate,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> Scheduling:
    try:
        async with redis.lock(
            SCHEDULING_LOCK_KEY,
            timeout=LOCK_TIMEOUT_SECONDS,
            blocking_timeout=LOCK_BLOCKING_TIMEOUT_SECONDS,
        ):
            return await scheduling_service.create_scheduling(db, data)
    except LockError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Another scheduling request is being processed, please try again",
        )
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("", response_model=list[SchedulingOut])
async def list_schedulings(
    date: datetime | None = None, db: AsyncSession = Depends(get_db)
) -> list[Scheduling]:
    query = select(Scheduling)
    if date is not None:
        if date.tzinfo is None:
            date = date.replace(tzinfo=LISBON_TZ)
        else:
            date = date.astimezone(LISBON_TZ)

        start_of_day = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)
        query = query.where(
            Scheduling.start_time >= start_of_day,
            Scheduling.start_time < end_of_day,
        )
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{scheduling_id}", response_model=SchedulingOut)
async def get_scheduling(scheduling_id: int, db: AsyncSession = Depends(get_db)) -> Scheduling:
    scheduling = await db.get(Scheduling, scheduling_id)
    if scheduling is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scheduling not found")
    return scheduling


@router.patch("/{scheduling_id}/complete-evaluation", response_model=SchedulingOut)
async def complete_evaluation(
    scheduling_id: int, data: CompleteEvaluationRequest, db: AsyncSession = Depends(get_db)
) -> Scheduling:
    try:
        return await scheduling_service.complete_evaluation(
            db, scheduling_id, data.estimated_duration_minutes
        )
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.patch("/{scheduling_id}/cancel", response_model=SchedulingOut)
async def cancel_scheduling(scheduling_id: int, db: AsyncSession = Depends(get_db)) -> Scheduling:
    try:
        return await scheduling_service.cancel_scheduling(db, scheduling_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))