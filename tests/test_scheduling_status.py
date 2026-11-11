from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client_model import Client
from app.models.service_model import Service, ServiceCategory
from app.models.scheduling_model import (
    Scheduling,
    AppointmentType,
    AppointmentStatus,
    effective_status,
)
from app.schemas.scheduling_schema import LISBON_TZ
from tests.test_scheduling import next_open_datetime


@pytest_asyncio.fixture
async def status_client(db_session: AsyncSession) -> Client:
    client_obj = Client(first_name="Ana", last_name="Costa")
    db_session.add(client_obj)
    await db_session.commit()
    await db_session.refresh(client_obj)
    return client_obj


@pytest_asyncio.fixture
async def status_service(db_session: AsyncSession) -> Service:
    service_obj = Service(
        name="Corte", category=ServiceCategory.COLOR_CUT, price_from=28, duration_minutes=60
    )
    db_session.add(service_obj)
    await db_session.commit()
    await db_session.refresh(service_obj)
    return service_obj


async def add_scheduling(
    db_session: AsyncSession,
    client_obj: Client,
    service_obj: Service,
    start: datetime,
    duration_minutes: int = 60,
    **kwargs,
) -> Scheduling:
    scheduling = Scheduling(
        client_id=client_obj.id,
        service_id=service_obj.id,
        start_time=start,
        end_time=start + timedelta(minutes=duration_minutes),
        type=kwargs.pop("type", AppointmentType.PROCEDURE),
        **kwargs,
    )
    db_session.add(scheduling)
    await db_session.commit()
    await db_session.refresh(scheduling)
    return scheduling


def test_effective_status_predicate():
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    past = now - timedelta(minutes=1)
    future = now + timedelta(minutes=1)

    assert effective_status(AppointmentStatus.CONFIRMED, past, now) == AppointmentStatus.COMPLETED
    assert effective_status(AppointmentStatus.CONFIRMED, now, now) == AppointmentStatus.COMPLETED
    assert effective_status(AppointmentStatus.CONFIRMED, future, now) == AppointmentStatus.CONFIRMED
    assert effective_status(AppointmentStatus.CANCELLED, past, now) == AppointmentStatus.CANCELLED


@pytest.mark.asyncio
async def test_future_scheduling_is_reported_as_confirmed(
    client: AsyncClient, auth_headers, db_session, status_client, status_service
):
    start = datetime.now(LISBON_TZ) + timedelta(days=3)
    scheduling = await add_scheduling(db_session, status_client, status_service, start)

    response = await client.get(f"/schedulings/{scheduling.id}", headers=auth_headers)

    assert response.json()["status"] == "confirmed"


@pytest.mark.asyncio
async def test_in_progress_scheduling_is_reported_as_confirmed(
    client: AsyncClient, auth_headers, db_session, status_client, status_service
):
    start = datetime.now(LISBON_TZ) - timedelta(minutes=30)
    scheduling = await add_scheduling(db_session, status_client, status_service, start)

    response = await client.get(f"/schedulings/{scheduling.id}", headers=auth_headers)

    assert response.json()["status"] == "confirmed"


@pytest.mark.asyncio
async def test_past_scheduling_is_reported_as_completed_but_stored_as_confirmed(
    client: AsyncClient, auth_headers, db_session, status_client, status_service
):
    start = datetime.now(LISBON_TZ) - timedelta(days=1)
    scheduling = await add_scheduling(db_session, status_client, status_service, start)

    get_response = await client.get(f"/schedulings/{scheduling.id}", headers=auth_headers)
    list_response = await client.get("/schedulings", headers=auth_headers)

    assert get_response.json()["status"] == "completed"
    assert list_response.json()[0]["status"] == "completed"

    await db_session.refresh(scheduling)
    assert scheduling.status == AppointmentStatus.CONFIRMED


@pytest.mark.asyncio
async def test_past_cancelled_scheduling_stays_cancelled(
    client: AsyncClient, auth_headers, db_session, status_client, status_service
):
    start = datetime.now(LISBON_TZ) - timedelta(days=1)
    scheduling = await add_scheduling(
        db_session, status_client, status_service, start, status=AppointmentStatus.CANCELLED
    )

    response = await client.get(f"/schedulings/{scheduling.id}", headers=auth_headers)

    assert response.json()["status"] == "cancelled"


# ---- Rules that depend on the stored status behave as before ----

@pytest.mark.asyncio
async def test_completed_scheduling_still_blocks_client_deletion(
    client: AsyncClient, auth_headers, db_session, status_client, status_service
):
    start = datetime.now(LISBON_TZ) - timedelta(days=1)
    await add_scheduling(db_session, status_client, status_service, start)

    response = await client.delete(f"/clients/{status_client.id}", headers=auth_headers)

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_completed_scheduling_can_still_be_cancelled(
    client: AsyncClient, auth_headers, db_session, status_client, status_service
):
    start = datetime.now(LISBON_TZ) - timedelta(days=1)
    scheduling = await add_scheduling(db_session, status_client, status_service, start)

    response = await client.patch(f"/schedulings/{scheduling.id}/cancel", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_past_evaluation_can_be_completed_and_linked_to_procedure(
    client: AsyncClient, auth_headers, db_session, status_client
):
    long_service = Service(
        name="Balayage",
        category=ServiceCategory.HAIR_TREATMENT,
        price_from=180,
        requires_evaluation=True,
    )
    db_session.add(long_service)
    await db_session.commit()
    await db_session.refresh(long_service)

    evaluation = await add_scheduling(
        db_session,
        status_client,
        long_service,
        datetime.now(LISBON_TZ) - timedelta(days=2),
        type=AppointmentType.EVALUATION,
    )

    evaluation_response = await client.get(
        f"/schedulings/{evaluation.id}", headers=auth_headers
    )
    assert evaluation_response.json()["status"] == "completed"

    complete_response = await client.patch(
        f"/schedulings/{evaluation.id}/complete-evaluation",
        json={"estimated_duration_minutes": 300},
        headers=auth_headers,
    )
    assert complete_response.status_code == 200

    procedure_response = await client.post(
        "/schedulings",
        json={
            "client_id": status_client.id,
            "service_id": long_service.id,
            "start_time": next_open_datetime(hour=10).isoformat(),
            "type": "procedure",
            "evaluation_id": evaluation.id,
        },
        headers=auth_headers,
    )
    assert procedure_response.status_code == 201
    assert procedure_response.json()["status"] == "confirmed"
