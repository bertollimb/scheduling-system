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