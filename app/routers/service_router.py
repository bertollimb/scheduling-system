from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, get_current_user
from app.models.service_model import Service
from app.models.scheduling_model import Scheduling, AppointmentStatus
from app.schemas.service_schema import ServiceCreate, ServiceUpdate, ServiceOut

router = APIRouter(
    prefix="/services",
    tags=["services"],
    dependencies=[Depends(get_current_user)],
)


@router.post("", response_model=ServiceOut, status_code=status.HTTP_201_CREATED)
async def create_service(data: ServiceCreate, db: AsyncSession = Depends(get_db)) -> Service:
    service = Service(**data.model_dump())
    db.add(service)
    await db.commit()
    await db.refresh(service)
    return service


@router.get("", response_model=list[ServiceOut])
async def list_services(db: AsyncSession = Depends(get_db)) -> list[Service]:
    result = await db.execute(select(Service))
    return list(result.scalars().all())


@router.get("/{service_id}", response_model=ServiceOut)
async def get_service(service_id: int, db: AsyncSession = Depends(get_db)) -> Service:
    service = await db.get(Service, service_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    return service


@router.patch("/{service_id}", response_model=ServiceOut)
async def update_service(
    service_id: int, data: ServiceUpdate, db: AsyncSession = Depends(get_db)
) -> Service:
    service = await db.get(Service, service_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(service, field, value)

    await db.commit()
    await db.refresh(service)
    return service


@router.delete("/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service(service_id: int, db: AsyncSession = Depends(get_db)) -> None:
    service = await db.get(Service, service_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")

    confirmed_exists = await db.execute(
        select(Scheduling).where(
            Scheduling.service_id == service_id,
            Scheduling.status == AppointmentStatus.CONFIRMED,
        )
    )
    if confirmed_exists.scalars().first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete a service with an active (confirmed) scheduling",
        )

    # Cancelled schedulings still reference this service at the database
    # level, which would otherwise block deletion via the foreign key
    # constraint. Only a confirmed scheduling is meant to protect a
    # service from being removed, so cancelled ones tied to this service
    # are deleted along with it.
    await db.execute(delete(Scheduling).where(Scheduling.service_id == service_id))

    try:
        await db.delete(service)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete a service with existing schedulings",
        )