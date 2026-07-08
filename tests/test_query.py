"""Unit tests for the GET /city/{city_name} endpoint.

Validates Requirements:
- 3.1: Returns 200 with city name and population for existing cities
- 3.2: Returns 404 when city does not exist
- 3.3: Case-insensitive lookup
- 3.4: Returns city name in originally stored casing
"""

from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_existing_city_returns_200_with_correct_body(async_client, mock_es_client):
    """GET /city/{city_name} returns 200 with city and population when city exists."""
    mock_es_client.get = AsyncMock(
        return_value={
            "_source": {"city_display_name": "London", "population": 9000000}
        }
    )

    response = await async_client.get("/city/london")

    assert response.status_code == 200
    body = response.json()
    assert body == {"city": "London", "population": 9000000}


@pytest.mark.asyncio
async def test_non_existent_city_returns_404(async_client, mock_es_client):
    """GET /city/{city_name} returns 404 with detail when city does not exist."""
    # mock_es_client.get already raises NotFoundError by default in conftest

    response = await async_client.get("/city/atlantis")

    assert response.status_code == 404
    body = response.json()
    assert "detail" in body


@pytest.mark.asyncio
async def test_case_insensitive_lookup_returns_original_casing(
    async_client, mock_es_client
):
    """GET /city/{city_name} performs case-insensitive lookup and returns original casing."""
    mock_es_client.get = AsyncMock(
        return_value={
            "_source": {"city_display_name": "New York", "population": 8300000}
        }
    )

    # Query with different casing than stored
    response = await async_client.get("/city/NEW YORK")

    assert response.status_code == 200
    body = response.json()
    # Should return the originally stored casing
    assert body["city"] == "New York"
    assert body["population"] == 8300000
