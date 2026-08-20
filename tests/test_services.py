import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_service(client: AsyncClient, auth_headers: dict[str, str]):
    response = await client.post(
        "/services",
        json={
            "name": "Corte c/ Finalização",
            "category": "color_cut",
            "price_from": "28.00",
            "duration_minutes": 90,
            "requires_evaluation": False,
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Corte c/ Finalização"
    assert data["category"] == "color_cut"
    assert data["price_from"] == "28.00"
    assert data["requires_evaluation"] is False
    assert "id" in data


@pytest.mark.asyncio
async def test_create_service_without_auth_fails(client: AsyncClient):
    response = await client.post(
        "/services",
        json={
            "name": "Corte c/ Finalização",
            "category": "color_cut",
            "price_from": "28.00",
        },
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_service_with_negative_price_fails(
    client: AsyncClient, auth_headers: dict[str, str]
):
    response = await client.post(
        "/services",
        json={
            "name": "Corte c/ Finalização",
            "category": "color_cut",
            "price_from": "-10.00",
        },
        headers=auth_headers,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_service_with_zero_price_fails(
    client: AsyncClient, auth_headers: dict[str, str]
):
    response = await client.post(
        "/services",
        json={
            "name": "Corte c/ Finalização",
            "category": "color_cut",
            "price_from": "0",
        },
        headers=auth_headers,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_service_with_invalid_category_fails(
    client: AsyncClient, auth_headers: dict[str, str]
):
    response = await client.post(
        "/services",
        json={
            "name": "Corte c/ Finalização",
            "category": "not_a_real_category",
            "price_from": "28.00",
        },
        headers=auth_headers,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_hair_treatment_service_requires_evaluation(
    client: AsyncClient, auth_headers: dict[str, str]
):
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

    assert response.status_code == 201
    data = response.json()
    assert data["requires_evaluation"] is True
    assert data["duration_minutes"] is None


@pytest.mark.asyncio
async def test_list_services(client: AsyncClient, auth_headers: dict[str, str]):
    await client.post(
        "/services",
        json={"name": "Hidratação Simples", "category": "treatment", "price_from": "35.00"},
        headers=auth_headers,
    )

    response = await client.get("/services", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Hidratação Simples"


@pytest.mark.asyncio
async def test_get_nonexistent_service_returns_404(
    client: AsyncClient, auth_headers: dict[str, str]
):
    response = await client.get("/services/9999", headers=auth_headers)

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_service_price(client: AsyncClient, auth_headers: dict[str, str]):
    create_response = await client.post(
        "/services",
        json={"name": "Retoque de Raiz", "category": "color_cut", "price_from": "35.00"},
        headers=auth_headers,
    )
    service_id = create_response.json()["id"]

    update_response = await client.patch(
        f"/services/{service_id}",
        json={"price_from": "40.00"},
        headers=auth_headers,
    )

    assert update_response.status_code == 200
    data = update_response.json()
    assert data["price_from"] == "40.00"
    assert data["name"] == "Retoque de Raiz"


@pytest.mark.asyncio
async def test_update_service_with_negative_price_fails(
    client: AsyncClient, auth_headers: dict[str, str]
):
    create_response = await client.post(
        "/services",
        json={"name": "Retoque de Raiz", "category": "color_cut", "price_from": "35.00"},
        headers=auth_headers,
    )
    service_id = create_response.json()["id"]

    update_response = await client.patch(
        f"/services/{service_id}",
        json={"price_from": "-5.00"},
        headers=auth_headers,
    )

    assert update_response.status_code == 422


@pytest.mark.asyncio
async def test_delete_service(client: AsyncClient, auth_headers: dict[str, str]):
    create_response = await client.post(
        "/services",
        json={"name": "Prancha", "category": "straightening", "price_from": "10.00"},
        headers=auth_headers,
    )
    service_id = create_response.json()["id"]

    delete_response = await client.delete(f"/services/{service_id}", headers=auth_headers)
    assert delete_response.status_code == 204

    get_response = await client.get(f"/services/{service_id}", headers=auth_headers)
    assert get_response.status_code == 404