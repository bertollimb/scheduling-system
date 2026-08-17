from datetime import datetime, timedelta, time

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client_model import Client
from app.models.service_model import Service, ServiceCategory
from app.models.scheduling_model import Scheduling, AppointmentType, AppointmentStatus
from app.schemas.scheduling_schema import SchedulingCreate

BUSINESS_START = time(10, 0)
BUSINESS_END = time(19, 0)
OPEN_WEEKDAYS = {1, 2, 3, 4, 5}  # Tuesday=1 ... Saturday=5 (Monday=0, Sunday=6)
EVALUATION_DURATION_MINUTES = 60
CANCELLATION_WINDOW_HOURS = 24
LONG_SERVICE_CATEGORIES = {ServiceCategory.HAIR_TREATMENT, ServiceCategory.STRAIGHTENING}


# ---- pure validation functions ----

def validate_business_hours(start_time: datetime, end_time: datetime) -> None:
    if start_time.weekday() not in OPEN_WEEKDAYS:
        raise ValueError("The salon is closed on this day")
    if start_time.time() < BUSINESS_START or end_time.time() > BUSINESS_END:
        raise ValueError("The appointment must be within business hours (10:00-19:00)")


def validate_start_time_for_long_services(service: Service, start_time: datetime) -> None:
    if service.category in LONG_SERVICE_CATEGORIES and start_time.time() != BUSINESS_START:
        raise ValueError(
            "Hair treatment and straightening services must start at opening time (10:00)"
        )


def calculate_end_time(
    service: Service, start_time: datetime, appointment_type: AppointmentType,
    evaluation: Scheduling | None = None,
) -> datetime:
    if appointment_type == AppointmentType.EVALUATION:
        return start_time + timedelta(minutes=EVALUATION_DURATION_MINUTES)

    if service.duration_minutes is not None:
        return start_time + timedelta(minutes=service.duration_minutes)

    if evaluation is not None and evaluation.estimated_duration_minutes is not None:
        return start_time + timedelta(minutes=evaluation.estimated_duration_minutes)

    raise ValueError("Unable to determine appointment duration")


def validate_evaluation_requirement(
    service: Service, client_id: int, evaluation: Scheduling | None
) -> None:
    if not service.requires_evaluation:
        return

    if evaluation is None:
        raise ValueError("This service requires a prior evaluation")
    if evaluation.type != AppointmentType.EVALUATION:
        raise ValueError("The referenced scheduling is not an evaluation")
    if evaluation.client_id != client_id:
        raise ValueError("The evaluation does not belong to this client")
    if evaluation.service_id != service.id:
        raise ValueError("The evaluation was not made for this service")
    if evaluation.estimated_duration_minutes is None:
        raise ValueError("The evaluation has not been completed yet")


# ---- database-dependent functions ----

async def check_overlap(db: AsyncSession, start_time: datetime, end_time: datetime) -> bool:
    result = await db.execute(
        select(Scheduling).where(
            and_(
                Scheduling.status != AppointmentStatus.CANCELLED,
                Scheduling.start_time < end_time,
                Scheduling.end_time > start_time,
            )
        )
    )
    return result.scalars().first() is not None


async def check_evaluation_already_used(db: AsyncSession, evaluation_id: int) -> bool:
    result = await db.execute(
        select(Scheduling).where(
            and_(
                Scheduling.evaluation_id == evaluation_id,
                Scheduling.status != AppointmentStatus.CANCELLED,
            )
        )
    )
    return result.scalars().first() is not None


async def create_scheduling(db: AsyncSession, data: SchedulingCreate) -> Scheduling:
    service = await db.get(Service, data.service_id)
    if service is None:
        raise ValueError("Service not found")

    client = await db.get(Client, data.client_id)
    if client is None:
        raise ValueError("Client not found")

    evaluation = None
    if data.evaluation_id is not None:
        evaluation = await db.get(Scheduling, data.evaluation_id)
        if evaluation is None:
            raise ValueError("Evaluation not found")

    if data.type == AppointmentType.PROCEDURE:
        validate_evaluation_requirement(service, data.client_id, evaluation)
        if evaluation is not None and await check_evaluation_already_used(db, evaluation.id):
            raise ValueError("This evaluation has already been used for another scheduling")

    end_time = calculate_end_time(service, data.start_time, data.type, evaluation)

    validate_business_hours(data.start_time, end_time)
    validate_start_time_for_long_services(service, data.start_time)

    if await check_overlap(db, data.start_time, end_time):
        raise ValueError("This time slot conflicts with an existing appointment")

    scheduling = Scheduling(
        client_id=data.client_id,
        service_id=data.service_id,
        start_time=data.start_time,
        end_time=end_time,
        type=data.type,
        evaluation_id=data.evaluation_id,
    )
    db.add(scheduling)
    await db.commit()
    await db.refresh(scheduling)
    return scheduling


async def complete_evaluation(
    db: AsyncSession, scheduling_id: int, estimated_duration_minutes: int
) -> Scheduling:
    scheduling = await db.get(Scheduling, scheduling_id)
    if scheduling is None:
        raise ValueError("Scheduling not found")
    if scheduling.type != AppointmentType.EVALUATION:
        raise ValueError("Only evaluations can be completed this way")
    if scheduling.estimated_duration_minutes is not None:
        raise ValueError("This evaluation has already been completed")

    scheduling.estimated_duration_minutes = estimated_duration_minutes
    await db.commit()
    await db.refresh(scheduling)
    return scheduling


async def cancel_scheduling(db: AsyncSession, scheduling_id: int) -> Scheduling:
    scheduling = await db.get(Scheduling, scheduling_id)
    if scheduling is None:
        raise ValueError("Scheduling not found")

    if scheduling.status != AppointmentStatus.CONFIRMED:
        raise ValueError("Only confirmed schedulings can be cancelled")

    hours_until_start = (scheduling.start_time - datetime.now(scheduling.start_time.tzinfo)) / timedelta(hours=1)
    if hours_until_start < CANCELLATION_WINDOW_HOURS:
        raise ValueError("Cancellations require at least 24 hours notice")

    scheduling.status = AppointmentStatus.CANCELLED
    await db.commit()
    await db.refresh(scheduling)
    return scheduling