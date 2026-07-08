"""Unit tests for validation and error handling.

Validates: Requirements 8.1, 8.2, 8.3, 8.4
"""

import pytest


@pytest.mark.asyncio
async def test_malformed_json_body_returns_422(async_client):
    """Sending a request with invalid JSON body returns 422.

    Validates: Requirement 8.4
    """
    response = await async_client.put(
        "/city/london",
        content=b"{invalid json",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422
    body = response.json()
    assert "detail" in body
    assert body["detail"] == "Request body is not valid JSON"


@pytest.mark.asyncio
async def test_internal_error_returns_500_with_generic_message(
    async_client, mock_es_client
):
    """Unexpected internal errors return 500 with no stack traces exposed.

    Validates: Requirement 8.2
    """
    # Configure mock to raise an unexpected error during the index operation
    mock_es_client.index.side_effect = RuntimeError(
        "something internal at /app/repository.py line 42"
    )

    response = await async_client.put(
        "/city/paris",
        json={"population": 2000000},
    )

    assert response.status_code == 500
    body = response.json()
    assert body == {"detail": "Internal server error"}
    # Ensure no stack traces or file paths leak
    response_text = response.text
    assert "Traceback" not in response_text
    assert "/app/" not in response_text
    assert "repository.py" not in response_text


@pytest.mark.asyncio
async def test_error_detail_truncated_to_500_characters(
    async_client, mock_es_client
):
    """Error detail field is truncated to 500 characters maximum.

    Validates: Requirements 8.1
    """
    # Use a city name long enough so "City '{name}' not found" exceeds 500 chars
    # The CityNotFoundError format is: "City '{city_name}' not found"
    # That's 7 + len(city_name) + 12 = 19 + len(city_name) chars
    # We need total > 500, so city_name > 481 chars
    # But city_name validation limits to 128 chars on PUT, so we use GET
    # which doesn't have the same path param validation in the route handler.
    # Actually, looking at get_city_endpoint, it calls get_city() from repository
    # which returns None for not found, then raises CityNotFoundError(city_name).
    # The city_not_found_handler uses _truncate_detail(str(exc)).
    # str(exc) = "City '{city_name}' not found"
    # We need a city_name that makes this > 500 chars.
    long_city_name = "a" * 500  # "City 'aaa...aaa' not found" = 519 chars

    # Mock get to raise NotFoundError so get_city returns None
    from elasticsearch import NotFoundError

    mock_es_client.get.side_effect = NotFoundError(
        404, "document_missing_exception", {}
    )

    response = await async_client.get(f"/city/{long_city_name}")

    assert response.status_code == 404
    body = response.json()
    assert "detail" in body
    assert len(body["detail"]) <= 500
