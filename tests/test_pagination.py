from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.configs import settings
from app.models.client_model import Client
from app.models.service_model import Service, ServiceCategory
from app.models.scheduling_model import Scheduling, AppointmentType
from app.schemas.scheduling_schema import LISBON_TZ

LIST_ENDPOINTS = ["/clients", "/services", "/schedulings"]


async def create_clients(client: AsyncClient, auth_headers: dict[str, str], count: int) -> list[int]:
    ids = []
    for i in range(count):
        response = await client.post(
            "/clients",
            json={"first_name": f"Client{i}", "last_name": "Test"},
            headers=auth_headers,
        )
        ids.append(response.json()["id"])
    return ids


@pytest.mark.asyncio
async def test_list_clients_respects_limit(client: AsyncClient, auth_headers: dict[str, str]):
    ids = await create_clients(client, auth_headers, 3)

    response = await client.get("/clients", params={"limit": 2}, headers=auth_headers)

    assert response.status_code == 200
    assert [c["id"] for c in response.json()] == ids[:2]
    assert response.headers["X-Total-Count"] == "3"


@pytest.mark.asyncio
async def test_list_clients_respects_skip(client: AsyncClient, auth_headers: dict[str, str]):
    ids = await create_clients(client, auth_headers, 3)

    response = await client.get("/clients", params={"skip": 2}, headers=auth_headers)

    assert response.status_code == 200
    assert [c["id"] for c in response.json()] == ids[2:]
    assert response.headers["X-Total-Count"] == "3"


@pytest.mark.asyncio
async def test_list_clients_order_is_stable(client: AsyncClient, auth_headers: dict[str, str]):
    ids = await create_clients(client, auth_headers, 4)

    first_page = await client.get("/clients", params={"limit": 2}, headers=auth_headers)
    second_page = await client.get(
        "/clients", params={"skip": 2, "limit": 2}, headers=auth_headers
    )

    returned = [c["id"] for c in first_page.json()] + [c["id"] for c in second_page.json()]
    assert returned == sorted(ids)


@pytest.mark.asyncio
async def test_list_services_respects_skip_and_limit(
    client: AsyncClient, auth_headers: dict[str, str]
):
    ids = []
    for i in range(3):
        response = await client.post(
            "/services",
            json={"name": f"Service{i}", "category": "treatment", "price_from": "10.00"},
            headers=auth_headers,
        )
        ids.append(response.json()["id"])

    response = await client.get(
        "/services", params={"skip": 1, "limit": 1}, headers=auth_headers
    )

    assert response.status_code == 200
    assert [s["id"] for s in response.json()] == ids[1:2]
    assert response.headers["X-Total-Count"] == "3"


@pytest.mark.asyncio
async def test_list_schedulings_total_count_uses_date_filter(
    client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession
):
    client_obj = Client(first_name="Ana", last_name="Costa")
    service_obj = Service(
        name="Corte", category=ServiceCategory.COLOR_CUT, price_from=28, duration_minutes=60
    )
    db_session.add_all([client_obj, service_obj])
    await db_session.commit()

    day = (datetime.now(LISBON_TZ) + timedelta(days=10)).replace(
        hour=10, minute=0, second=0, microsecond=0
    )
    starts = [day, day + timedelta(hours=2), day + timedelta(days=1)]
    for start in starts:
        db_session.add(
            Scheduling(
                client_id=client_obj.id,
                service_id=service_obj.id,
                start_time=start,
                end_time=start + timedelta(minutes=60),
                type=AppointmentType.PROCEDURE,
            )
        )
    await db_session.commit()

    all_response = await client.get("/schedulings", headers=auth_headers)
    day_response = await client.get(
        "/schedulings", params={"date": day.isoformat(), "limit": 1}, headers=auth_headers
    )

    assert all_response.headers["X-Total-Count"] == "3"
    ids = [s["id"] for s in all_response.json()]
    assert ids == sorted(ids)

    assert len(day_response.json()) == 1
    assert day_response.headers["X-Total-Count"] == "2"


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", LIST_ENDPOINTS)
async def test_list_max_limit_is_accepted(
    client: AsyncClient, auth_headers: dict[str, str], endpoint: str
):
    response = await client.get(endpoint, params={"limit": 5000}, headers=auth_headers)

    assert response.status_code == 200
    assert response.headers["X-Total-Count"] == "0"


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", LIST_ENDPOINTS)
@pytest.mark.parametrize("params", [{"limit": 5001}, {"limit": 0}, {"skip": -1}])
async def test_list_invalid_pagination_fails(
    client: AsyncClient, auth_headers: dict[str, str], endpoint: str, params: dict
):
    response = await client.get(endpoint, params=params, headers=auth_headers)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_total_count_header_is_exposed_to_cors(
    client: AsyncClient, auth_headers: dict[str, str]
):
    origin = settings.cors_origins[0]

    response = await client.get(
        "/clients", headers={**auth_headers, "Origin": origin}
    )

    assert response.status_code == 200
    exposed = response.headers.get("access-control-expose-headers", "")
    assert "x-total-count" in exposed.lower()
