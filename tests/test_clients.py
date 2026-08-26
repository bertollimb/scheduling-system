import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_client(client: AsyncClient, auth_headers: dict[str, str]):
    response = await client.post(
        "/clients",
        json={
            "first_name": "Maria",
            "last_name": "Silva",
            "phone": "912345678",
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["first_name"] == "Maria"
    assert data["last_name"] == "Silva"
    assert data["phone"] == "912345678"
    assert "id" in data


@pytest.mark.asyncio
async def test_create_client_without_auth_fails(client: AsyncClient):
    response = await client.post(
        "/clients",
        json={"first_name": "Maria", "last_name": "Silva", "phone": "912345678"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_client_with_empty_name_fails(client: AsyncClient, auth_headers: dict[str, str]):
    response = await client.post(
        "/clients",
        json={"first_name": "", "last_name": "Silva", "phone": "912345678"},
        headers=auth_headers,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_clients(client: AsyncClient, auth_headers: dict[str, str]):
    await client.post(
        "/clients",
        json={"first_name": "Ana", "last_name": "Costa", "phone": "911111111"},
        headers=auth_headers,
    )

    response = await client.get("/clients", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["first_name"] == "Ana"


@pytest.mark.asyncio
async def test_get_nonexistent_client_returns_404(client: AsyncClient, auth_headers: dict[str, str]):
    response = await client.get("/clients/9999", headers=auth_headers)

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_client_partial(client: AsyncClient, auth_headers: dict[str, str]):
    create_response = await client.post(
        "/clients",
        json={"first_name": "Pedro", "last_name": "Alves", "phone": "922222222"},
        headers=auth_headers,
    )
    client_id = create_response.json()["id"]

    update_response = await client.patch(
        f"/clients/{client_id}",
        json={"phone": "933333333"},
        headers=auth_headers,
    )

    assert update_response.status_code == 200
    data = update_response.json()
    assert data["phone"] == "933333333"
    assert data["first_name"] == "Pedro"


@pytest.mark.asyncio
async def test_delete_client(client: AsyncClient, auth_headers: dict[str, str]):
    create_response = await client.post(
        "/clients",
        json={"first_name": "Rita", "last_name": "Nunes", "phone": "944444444"},
        headers=auth_headers,
    )
    client_id = create_response.json()["id"]

    delete_response = await client.delete(f"/clients/{client_id}", headers=auth_headers)
    assert delete_response.status_code == 204

    get_response = await client.get(f"/clients/{client_id}", headers=auth_headers)
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_delete_client_with_confirmed_scheduling_fails(
    client: AsyncClient, auth_headers: dict[str, str]
):
    from datetime import datetime, timedelta
    from app.schemas.scheduling_schema import LISBON_TZ

    client_response = await client.post(
        "/clients",
        json={"first_name": "Lucia", "last_name": "Alves", "phone": "955555555"},
        headers=auth_headers,
    )
    client_id = client_response.json()["id"]

    service_response = await client.post(
        "/services",
        json={"name": "Corte", "category": "color_cut", "price_from": "20.00", "duration_minutes": 30},
        headers=auth_headers,
    )
    service_id = service_response.json()["id"]

    start = datetime.now(LISBON_TZ) + timedelta(days=7)
    while start.weekday() not in {1, 2, 3, 4, 5}:
        start += timedelta(days=1)
    start = start.replace(hour=10, minute=0, second=0, microsecond=0)

    await client.post(
        "/schedulings",
        json={
            "client_id": client_id,
            "service_id": service_id,
            "start_time": start.isoformat(),
            "type": "procedure",
        },
        headers=auth_headers,
    )

    delete_response = await client.delete(f"/clients/{client_id}", headers=auth_headers)
    assert delete_response.status_code == 409


@pytest.mark.asyncio
async def test_delete_client_with_only_cancelled_schedulings_succeeds(
    client: AsyncClient, auth_headers: dict[str, str]
):
    from datetime import datetime, timedelta
    from app.schemas.scheduling_schema import LISBON_TZ

    client_response = await client.post(
        "/clients",
        json={"first_name": "Rui", "last_name": "Pinto", "phone": "966666666"},
        headers=auth_headers,
    )
    client_id = client_response.json()["id"]

    service_response = await client.post(
        "/services",
        json={"name": "Corte", "category": "color_cut", "price_from": "20.00", "duration_minutes": 30},
        headers=auth_headers,
    )
    service_id = service_response.json()["id"]

    start = datetime.now(LISBON_TZ) + timedelta(days=7)
    while start.weekday() not in {1, 2, 3, 4, 5}:
        start += timedelta(days=1)
    start = start.replace(hour=10, minute=0, second=0, microsecond=0)

    scheduling_response = await client.post(
        "/schedulings",
        json={
            "client_id": client_id,
            "service_id": service_id,
            "start_time": start.isoformat(),
            "type": "procedure",
        },
        headers=auth_headers,
    )
    scheduling_id = scheduling_response.json()["id"]

    cancel_response = await client.patch(
        f"/schedulings/{scheduling_id}/cancel", headers=auth_headers
    )
    assert cancel_response.status_code == 200

    delete_response = await client.delete(f"/clients/{client_id}", headers=auth_headers)
    assert delete_response.status_code == 204