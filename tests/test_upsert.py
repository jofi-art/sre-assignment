"""Unit tests for PUT /city/{city_name} upsert endpoint."""

import pytest


# --- Test: New city returns 201 with correct body (Requirement 2.1, 2.2) ---


async def test_upsert_new_city_returns_201(async_client, mock_es_client):
    """PUT a new city should return 201 with the city name and population."""
    # mock_es_client.index already returns {"result": "created"} by default
    response = await async_client.put(
        "/city/Berlin", json={"population": 3_645_000}
    )

    assert response.status_code == 201
    data = response.json()
    assert data["city"] == "Berlin"
    assert data["population"] == 3_645_000


# --- Test: Existing city update returns 200 (Requirement 2.3) ---


async def test_upsert_existing_city_returns_200(async_client, mock_es_client):
    """PUT an existing city should return 200 with the updated population."""
    mock_es_client.index.return_value = {
        "result": "updated",
        "_id": "london",
        "_version": 2,
    }

    response = await async_client.put(
        "/city/London", json={"population": 9_000_000}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["city"] == "London"
    assert data["population"] == 9_000_000


# --- Test: Invalid population values return 422 (Requirement 2.4) ---


@pytest.mark.parametrize(
    "population,description",
    [
        (-1, "negative population"),
        (100_000_000_000, "population exceeds max"),
        ("not_a_number", "non-integer population"),
    ],
)
async def test_upsert_invalid_population_returns_422(
    async_client, mock_es_client, population, description
):
    """PUT with an invalid population value should return 422."""
    response = await async_client.put(
        "/city/Berlin", json={"population": population}
    )

    assert response.status_code == 422, f"Failed for: {description}"
    data = response.json()
    assert "detail" in data


# --- Test: Invalid city names return 422 (Requirement 2.5) ---


@pytest.mark.parametrize(
    "city_name,description",
    [
        ("%20%20", "whitespace-only city name"),
        ("A" * 129, "city name exceeds 128 characters"),
    ],
)
async def test_upsert_invalid_city_name_returns_422(
    async_client, mock_es_client, city_name, description
):
    """PUT with an invalid city name should return 422."""
    response = await async_client.put(
        f"/city/{city_name}", json={"population": 1000}
    )

    assert response.status_code == 422, f"Failed for: {description}"
    data = response.json()
    assert "detail" in data
