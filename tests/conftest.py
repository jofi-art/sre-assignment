"""Test fixtures and configuration for the City Population API test suite."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.exceptions import register_exception_handlers
from app.routes import router


# --- Test Settings ---


@pytest.fixture(autouse=True)
def set_test_env_vars(monkeypatch):
    """Set required environment variables for all tests."""
    monkeypatch.setenv("ELASTICSEARCH_HOST", "localhost")
    monkeypatch.setenv("ELASTICSEARCH_PORT", "9200")
    monkeypatch.setenv("ELASTICSEARCH_SCHEME", "http")
    monkeypatch.setenv("INDEX_NAME", "test_cities")
    monkeypatch.setenv("ES_TIMEOUT", "3")


@pytest.fixture
def test_settings() -> Settings:
    """Return a Settings instance for testing (does not read real env)."""
    return Settings(
        elasticsearch_host="localhost",
        elasticsearch_port=9200,
        elasticsearch_scheme="http",
        index_name="test_cities",
        es_timeout=3,
    )


# --- Mock Elasticsearch Client ---


@pytest.fixture
def mock_es_client() -> AsyncMock:
    """Create a mock AsyncElasticsearch client with default successful responses.

    The mock is pre-configured so that:
    - ping() returns True
    - indices.exists() returns False (index doesn't exist yet)
    - indices.create() succeeds
    - index() returns a 'created' result
    - get() raises NotFoundError (no documents by default)
    - close() succeeds
    """
    client = AsyncMock()

    # Health check
    client.ping = AsyncMock(return_value=True)

    # Index management
    client.indices = AsyncMock()
    client.indices.exists = AsyncMock(return_value=False)
    client.indices.create = AsyncMock(return_value={"acknowledged": True})

    # Document operations - default to 'created' for upserts
    client.index = AsyncMock(
        return_value={"result": "created", "_id": "test", "_version": 1}
    )
    # Default: get raises NotFoundError (no documents stored)
    from elasticsearch import NotFoundError

    client.get = AsyncMock(
        side_effect=NotFoundError(404, "document_missing_exception", {})
    )

    # Close
    client.close = AsyncMock(return_value=None)

    return client


# --- FastAPI Test Client ---


@pytest_asyncio.fixture
async def async_client(mock_es_client, test_settings):
    """Create an async HTTP test client with mocked ES dependencies.

    Builds a fresh FastAPI application with a no-op lifespan that directly
    injects the mock ES client and test settings into app.state. This avoids
    any dependency on a real Elasticsearch instance.
    """

    @asynccontextmanager
    async def _test_lifespan(app: FastAPI):
        # Inject test dependencies into app state (mirrors real lifespan)
        app.state.settings = test_settings
        app.state.es_client = mock_es_client
        yield

    # Build a fresh app for each test to avoid cross-test contamination
    test_app = FastAPI(title="City Population API", lifespan=_test_lifespan)
    test_app.include_router(router)
    register_exception_handlers(test_app)

    # Use httpx AsyncClient with the ASGI app directly
    # raise_app_exceptions=False ensures exception handlers return proper HTTP responses
    # instead of re-raising exceptions to the test runner
    async with AsyncClient(
        transport=ASGITransport(app=test_app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        # Manually trigger the lifespan startup by sending a lifespan scope
        # httpx ASGITransport doesn't send lifespan events, so we set state directly
        test_app.state.settings = test_settings
        test_app.state.es_client = mock_es_client
        yield client
