import asyncio
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client_model import Client
from app.models.service_model import Service, ServiceCategory
from app.models.scheduling_model import Scheduling, AppointmentType, AppointmentStatus
from app.schemas.scheduling_schema import LISBON_TZ
from app.services import scheduling_service

OPEN_WEEKDAYS = {1, 2, 3, 4, 5}  # Tuesday..Saturday


def next_open_datetime(hour: int = 10, days_ahead: int = 7) -> datetime:
    dt = datetime.now(LISBON_TZ) + timedelta(days=days_ahead)
    while dt.weekday() not in OPEN_WEEKDAYS:
        dt += timedelta(days=1)
    return dt.replace(hour=hour, minute=0, second=0, microsecond=0)


def next_closed_datetime(hour: int = 10, days_ahead: int = 7) -> datetime:
    dt = datetime.now(LISBON_TZ) + timedelta(days=days_ahead)
    while dt.weekday() in OPEN_WEEKDAYS:
        dt += timedelta(days=1)
    return dt.replace(hour=hour, minute=0, second=0, microsecond=0)


@pytest_asyncio.fixture
async def booked_client_id(client: AsyncClient, auth_headers: dict[str, str]) -> int:
    response = await client.post(
        "/clients",
        json={"first_name": "Maria", "last_name": "Silva", "phone": "912345678"},
        headers=auth_headers,
    )
    return response.json()["id"]


@pytest_asyncio.fixture
async def service_id(client: AsyncClient, auth_headers: dict[str, str]) -> int:
    response = await client.post(
        "/services",
        json={
            "name": "Corte c/ Finalização",
            "category": "color_cut",
            "price_from": "28.00",
            "duration_minutes": 90,
        },
        headers=auth_headers,
    )
    return response.json()["id"]


@pytest_asyncio.fixture
async def long_service_id(client: AsyncClient, auth_headers: dict[str, str]) -> int:
    response = await client.post(
        "/services",
        json={
            "name": "Balayage",
            "category": "hair_treatment",
            "price_from": "180.00",
            "requires_evaluation": True,
        },
        headers=auth_headers,
    )
    return response.json()["id"]


# ---- API-level tests: create_scheduling via HTTP ----

@pytest.mark.asyncio
async def test_create_procedure_success(
    client: AsyncClient, auth_headers, booked_client_id, service_id
):
    start = next_open_datetime(hour=10)
    response = await client.post(
        "/schedulings",
        json={
            "client_id": booked_client_id,
            "service_id": service_id,
            "start_time": start.isoformat(),
            "type": "procedure",
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "confirmed"


@pytest.mark.asyncio
async def test_create_scheduling_outside_business_hours_fails(
    client: AsyncClient, auth_headers, booked_client_id, service_id
):
    start = next_open_datetime(hour=18, days_ahead=7)  # 18:00 + 90min ends at 19:30, past closing
    response = await client.post(
        "/schedulings",
        json={
            "client_id": booked_client_id,
            "service_id": service_id,
            "start_time": start.isoformat(),
            "type": "procedure",
        },
        headers=auth_headers,
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_create_scheduling_on_closed_day_fails(
    client: AsyncClient, auth_headers, booked_client_id, service_id
):
    start = next_closed_datetime(hour=10)
    response = await client.post(
        "/schedulings",
        json={
            "client_id": booked_client_id,
            "service_id": service_id,
            "start_time": start.isoformat(),
            "type": "procedure",
        },
        headers=auth_headers,
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_create_scheduling_in_the_past_fails(
    client: AsyncClient, auth_headers, booked_client_id, service_id
):
    start = datetime.now(LISBON_TZ) - timedelta(days=1)
    response = await client.post(
        "/schedulings",
        json={
            "client_id": booked_client_id,
            "service_id": service_id,
            "start_time": start.isoformat(),
            "type": "procedure",
        },
        headers=auth_headers,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_evaluation_for_service_not_requiring_it_fails(
    client: AsyncClient, auth_headers, booked_client_id, service_id
):
    start = next_open_datetime(hour=11)
    response = await client.post(
        "/schedulings",
        json={
            "client_id": booked_client_id,
            "service_id": service_id,
            "start_time": start.isoformat(),
            "type": "evaluation",
        },
        headers=auth_headers,
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_evaluation_for_long_service_can_start_any_time(
    client: AsyncClient, auth_headers, booked_client_id, long_service_id
):
    start = next_open_datetime(hour=14)  # not opening time - should still be allowed
    response = await client.post(
        "/schedulings",
        json={
            "client_id": booked_client_id,
            "service_id": long_service_id,
            "start_time": start.isoformat(),
            "type": "evaluation",
        },
        headers=auth_headers,
    )

    assert response.status_code == 201


@pytest.mark.asyncio
async def test_procedure_for_long_service_without_evaluation_fails(
    client: AsyncClient, auth_headers, booked_client_id, long_service_id
):
    start = next_open_datetime(hour=10)
    response = await client.post(
        "/schedulings",
        json={
            "client_id": booked_client_id,
            "service_id": long_service_id,
            "start_time": start.isoformat(),
            "type": "procedure",
        },
        headers=auth_headers,
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_full_evaluation_to_procedure_flow(
    client: AsyncClient, auth_headers, booked_client_id, long_service_id
):
    # Evaluation and procedure are booked on different days on purpose:
    # a 6h procedure starting at 10:00 would otherwise overlap a same-day
    # 14:00 evaluation, which is a real conflict, not a test bug to hide.
    eval_start = next_open_datetime(hour=14, days_ahead=7)
    proc_start = next_open_datetime(hour=10, days_ahead=14)

    # 1. create evaluation
    eval_response = await client.post(
        "/schedulings",
        json={
            "client_id": booked_client_id,
            "service_id": long_service_id,
            "start_time": eval_start.isoformat(),
            "type": "evaluation",
        },
        headers=auth_headers,
    )
    assert eval_response.status_code == 201
    evaluation_id = eval_response.json()["id"]

    # 2. procedure attempt before completing evaluation fails
    early_attempt = await client.post(
        "/schedulings",
        json={
            "client_id": booked_client_id,
            "service_id": long_service_id,
            "start_time": proc_start.isoformat(),
            "type": "procedure",
            "evaluation_id": evaluation_id,
        },
        headers=auth_headers,
    )
    assert early_attempt.status_code == 400

    # 3. complete the evaluation
    complete_response = await client.patch(
        f"/schedulings/{evaluation_id}/complete-evaluation",
        json={"estimated_duration_minutes": 360},
        headers=auth_headers,
    )
    assert complete_response.status_code == 200

    # 4. procedure at the wrong start time (not opening) still fails
    wrong_time_attempt = await client.post(
        "/schedulings",
        json={
            "client_id": booked_client_id,
            "service_id": long_service_id,
            "start_time": proc_start.replace(hour=11).isoformat(),
            "type": "procedure",
            "evaluation_id": evaluation_id,
        },
        headers=auth_headers,
    )
    assert wrong_time_attempt.status_code == 400

    # 5. procedure at opening time succeeds
    success_attempt = await client.post(
        "/schedulings",
        json={
            "client_id": booked_client_id,
            "service_id": long_service_id,
            "start_time": proc_start.isoformat(),
            "type": "procedure",
            "evaluation_id": evaluation_id,
        },
        headers=auth_headers,
    )
    assert success_attempt.status_code == 201

    # 6. reusing the same evaluation for a second procedure fails
    reuse_attempt = await client.post(
        "/schedulings",
        json={
            "client_id": booked_client_id,
            "service_id": long_service_id,
            "start_time": next_open_datetime(hour=10, days_ahead=21).isoformat(),
            "type": "procedure",
            "evaluation_id": evaluation_id,
        },
        headers=auth_headers,
    )
    assert reuse_attempt.status_code == 400

    # 7. completing the same evaluation twice fails
    complete_again = await client.patch(
        f"/schedulings/{evaluation_id}/complete-evaluation",
        json={"estimated_duration_minutes": 300},
        headers=auth_headers,
    )
    assert complete_again.status_code == 400


@pytest.mark.asyncio
async def test_estimated_duration_out_of_range_fails(
    client: AsyncClient, auth_headers, booked_client_id, long_service_id
):
    eval_start = next_open_datetime(hour=14)
    eval_response = await client.post(
        "/schedulings",
        json={
            "client_id": booked_client_id,
            "service_id": long_service_id,
            "start_time": eval_start.isoformat(),
            "type": "evaluation",
        },
        headers=auth_headers,
    )
    evaluation_id = eval_response.json()["id"]

    too_short = await client.patch(
        f"/schedulings/{evaluation_id}/complete-evaluation",
        json={"estimated_duration_minutes": 100},
        headers=auth_headers,
    )
    assert too_short.status_code == 422

    too_long = await client.patch(
        f"/schedulings/{evaluation_id}/complete-evaluation",
        json={"estimated_duration_minutes": 600},
        headers=auth_headers,
    )
    assert too_long.status_code == 422


@pytest.mark.asyncio
async def test_overlapping_schedulings_conflict(
    client: AsyncClient, auth_headers, booked_client_id, service_id
):
    start = next_open_datetime(hour=10)

    first = await client.post(
        "/schedulings",
        json={
            "client_id": booked_client_id,
            "service_id": service_id,
            "start_time": start.isoformat(),
            "type": "procedure",
        },
        headers=auth_headers,
    )
    assert first.status_code == 201

    second = await client.post(
        "/schedulings",
        json={
            "client_id": booked_client_id,
            "service_id": service_id,
            "start_time": start.isoformat(),
            "type": "procedure",
        },
        headers=auth_headers,
    )
    assert second.status_code == 400


@pytest.mark.asyncio
async def test_concurrent_requests_prevent_double_booking(
    client: AsyncClient, auth_headers, booked_client_id, service_id
):
    start = next_open_datetime(hour=10)
    payload = {
        "client_id": booked_client_id,
        "service_id": service_id,
        "start_time": start.isoformat(),
        "type": "procedure",
    }

    results = await asyncio.gather(
        client.post("/schedulings", json=payload, headers=auth_headers),
        client.post("/schedulings", json=payload, headers=auth_headers),
    )

    status_codes = sorted(r.status_code for r in results)
    assert status_codes == [201, 400]


# ---- Service-layer tests: cancellation window, tested directly ----

@pytest_asyncio.fixture
async def db_client(db_session: AsyncSession) -> Client:
    client_obj = Client(first_name="Ana", last_name="Costa", phone="911111111")
    db_session.add(client_obj)
    await db_session.commit()
    await db_session.refresh(client_obj)
    return client_obj


@pytest_asyncio.fixture
async def db_service(db_session: AsyncSession) -> Service:
    service_obj = Service(
        name="Corte", category=ServiceCategory.COLOR_CUT, price_from=28, duration_minutes=90
    )
    db_session.add(service_obj)
    await db_session.commit()
    await db_session.refresh(service_obj)
    return service_obj


@pytest.mark.asyncio
async def test_cancel_with_enough_notice_succeeds(
    db_session: AsyncSession, db_client: Client, db_service: Service
):
    start = datetime.now(LISBON_TZ) + timedelta(days=2)
    scheduling = Scheduling(
        client_id=db_client.id,
        service_id=db_service.id,
        start_time=start,
        end_time=start + timedelta(minutes=90),
        type=AppointmentType.PROCEDURE,
    )
    db_session.add(scheduling)
    await db_session.commit()
    await db_session.refresh(scheduling)

    result = await scheduling_service.cancel_scheduling(db_session, scheduling.id)

    assert result.status == AppointmentStatus.CANCELLED


@pytest.mark.asyncio
async def test_cancel_without_enough_notice_fails(
    db_session: AsyncSession, db_client: Client, db_service: Service
):
    start = datetime.now(LISBON_TZ) + timedelta(hours=2)
    scheduling = Scheduling(
        client_id=db_client.id,
        service_id=db_service.id,
        start_time=start,
        end_time=start + timedelta(minutes=90),
        type=AppointmentType.PROCEDURE,
    )
    db_session.add(scheduling)
    await db_session.commit()
    await db_session.refresh(scheduling)

    with pytest.raises(ValueError, match="24 hours"):
        await scheduling_service.cancel_scheduling(db_session, scheduling.id)


@pytest.mark.asyncio
async def test_cancel_already_cancelled_fails(
    db_session: AsyncSession, db_client: Client, db_service: Service
):
    start = datetime.now(LISBON_TZ) + timedelta(days=2)
    scheduling = Scheduling(
        client_id=db_client.id,
        service_id=db_service.id,
        start_time=start,
        end_time=start + timedelta(minutes=90),
        type=AppointmentType.PROCEDURE,
        status=AppointmentStatus.CANCELLED,
    )
    db_session.add(scheduling)
    await db_session.commit()
    await db_session.refresh(scheduling)

    with pytest.raises(ValueError, match="confirmed"):
        await scheduling_service.cancel_scheduling(db_session, scheduling.id)