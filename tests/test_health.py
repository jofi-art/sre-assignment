"""Unit tests for the GET /health endpoint.

Validates Requirements:
- 1.1: Returns 200 with {"status": "ok"} when ES is reachable
- 1.2: Returns 503 with status "unavailable" when ES is down
- 1.3: Health check respects the 3-second timeout
"""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_health_returns_200_when_es_reachable(async_client, mock_es_client):
    """GET /health returns 200 with {"status": "ok"} when ES ping succeeds."""
    # mock_es_client.ping already returns True by default
    response = await async_client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body == {"status": "ok"}


@pytest.mark.asyncio
async def test_health_returns_503_when_es_down(async_client, mock_es_client):
    """GET /health returns 503 with status "unavailable" when ES is unreachable."""
    mock_es_client.ping = AsyncMock(return_value=False)

    response = await async_client.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable"
    assert "detail" in body


@pytest.mark.asyncio
async def test_health_respects_timeout(async_client, mock_es_client):
    """Health check calls check_es_health with the configured timeout value (3)."""
    with patch("app.routes.check_es_health", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = True

        response = await async_client.get("/health")

        assert response.status_code == 200
        # Verify check_es_health was called with the ES client and timeout=3
        mock_check.assert_called_once()
        call_args = mock_check.call_args
        # Second positional arg (or keyword) should be the timeout value
        assert call_args[0][1] == 3 or call_args.kwargs.get("timeout") == 3
