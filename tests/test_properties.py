"""Property-based tests for the City Population API.

Uses Hypothesis to verify correctness properties across many generated inputs.
"""

import re
import string
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from hypothesis import given, settings, strategies as st, assume
from fastapi import FastAPI

from app.config import Settings
from app.exceptions import register_exception_handlers
from app.routes import router
from elasticsearch import NotFoundError


# --- Strategies ---

# Valid city name: 1-128 printable characters that are URL-safe for path segments.
# Excludes: non-printable chars, '/', '#', '?', '%' (which break URL parsing)
# Also excludes '.' to avoid URL path resolution issues (. and .. are special)
_CITY_NAME_ALPHABET = string.ascii_letters + string.digits + " -_'()"

valid_city_name_strategy = st.text(
    alphabet=_CITY_NAME_ALPHABET,
    min_size=1,
    max_size=128,
).filter(lambda s: s.strip() != "")

# Valid population: 0 to 99,999,999,999
valid_population_strategy = st.integers(min_value=0, max_value=99_999_999_999)


# --- Helper: Create a test app with dict-based in-memory ES mock ---


def _create_storing_mock_es_client():
    """Create a mock ES client that stores/retrieves documents using an in-memory dict."""
    store: dict[str, dict] = {}
    client = AsyncMock()

    async def mock_index(index, id, document, refresh=None):
        is_new = id not in store
        store[id] = document
        return {"result": "created" if is_new else "updated"}

    async def mock_get(index, id):
        if id in store:
            return {"_source": store[id]}
        raise NotFoundError(404, "document_missing_exception", {})

    client.index = AsyncMock(side_effect=mock_index)
    client.get = AsyncMock(side_effect=mock_get)
    client.ping = AsyncMock(return_value=True)
    client.indices = AsyncMock()
    client.indices.exists = AsyncMock(return_value=True)
    client.close = AsyncMock(return_value=None)

    return client, store


def _create_notfound_mock_es_client():
    """Create a mock ES client where get always raises NotFoundError."""
    client = AsyncMock()

    async def mock_get(index, id):
        raise NotFoundError(404, "document_missing_exception", {})

    client.get = AsyncMock(side_effect=mock_get)
    client.index = AsyncMock(return_value={"result": "created"})
    client.ping = AsyncMock(return_value=True)
    client.indices = AsyncMock()
    client.indices.exists = AsyncMock(return_value=True)
    client.close = AsyncMock(return_value=None)

    return client


async def _make_client(es_client):
    """Create an httpx AsyncClient with the given ES mock wired into the app."""
    test_settings = Settings(
        elasticsearch_host="localhost",
        elasticsearch_port=9200,
        elasticsearch_scheme="http",
        index_name="test_cities",
        es_timeout=3,
    )

    @asynccontextmanager
    async def _test_lifespan(app: FastAPI):
        app.state.settings = test_settings
        app.state.es_client = es_client
        yield

    test_app = FastAPI(title="City Population API", lifespan=_test_lifespan)
    test_app.include_router(router)
    register_exception_handlers(test_app)

    client = AsyncClient(
        transport=ASGITransport(app=test_app, raise_app_exceptions=False),
        base_url="http://test",
    )
    # Set state directly since ASGITransport doesn't trigger lifespan
    test_app.state.settings = test_settings
    test_app.state.es_client = es_client
    return client


# --- Property 1: Upsert-then-retrieve round trip ---


@settings(max_examples=100)
@given(
    city_name=valid_city_name_strategy,
    population=valid_population_strategy,
)
@pytest.mark.asyncio
async def test_upsert_then_retrieve_round_trip(city_name, population):
    """Property 1: For any valid city name and population, PUT then GET returns the same values.

    Feature: sre-city-population-api, Property 1: Upsert-then-retrieve round trip
    **Validates: Requirements 2.1, 2.2, 3.1**
    """
    es_client, store = _create_storing_mock_es_client()
    async with await _make_client(es_client) as client:
        # PUT the city
        put_response = await client.put(
            f"/city/{city_name}",
            json={"population": population},
        )
        assert put_response.status_code in (200, 201)

        # GET the city
        get_response = await client.get(f"/city/{city_name}")
        assert get_response.status_code == 200

        data = get_response.json()
        assert data["city"] == city_name
        assert data["population"] == population


# --- Property 2: Update overwrites population ---


@settings(max_examples=100)
@given(
    city_name=valid_city_name_strategy,
    population1=valid_population_strategy,
    population2=valid_population_strategy,
)
@pytest.mark.asyncio
async def test_update_overwrites_population(city_name, population1, population2):
    """Property 2: Storing with P1 then P2 results in GET returning P2.

    Feature: sre-city-population-api, Property 2: Update overwrites population
    **Validates: Requirements 2.3**
    """
    assume(population1 != population2)

    es_client, store = _create_storing_mock_es_client()
    async with await _make_client(es_client) as client:
        # PUT with P1
        resp1 = await client.put(
            f"/city/{city_name}",
            json={"population": population1},
        )
        assert resp1.status_code in (200, 201)

        # PUT with P2
        resp2 = await client.put(
            f"/city/{city_name}",
            json={"population": population2},
        )
        assert resp2.status_code in (200, 201)

        # GET should return P2
        get_response = await client.get(f"/city/{city_name}")
        assert get_response.status_code == 200

        data = get_response.json()
        assert data["population"] == population2


# --- Property 3: Case-insensitive storage and retrieval with original casing preserved ---


# Strategy for city names that have meaningful case variations (contain letters)
_case_sensitive_city_name_strategy = st.text(
    alphabet=string.ascii_letters,
    min_size=1,
    max_size=64,
).filter(lambda s: s.strip() != "" and s.swapcase() != s)


@settings(max_examples=100)
@given(
    city_name=_case_sensitive_city_name_strategy,
    population=valid_population_strategy,
)
@pytest.mark.asyncio
async def test_case_insensitive_storage_preserves_original_casing(city_name, population):
    """Property 3: Storing with one casing and retrieving with another returns the original casing.

    Feature: sre-city-population-api, Property 3: Case-insensitive storage and retrieval with original casing preserved
    **Validates: Requirements 2.6, 3.3, 3.4**
    """
    # Create an alternate casing of the same city name
    alternate_casing = city_name.swapcase()
    assume(alternate_casing.lower() == city_name.lower())
    assume(alternate_casing != city_name)

    es_client, store = _create_storing_mock_es_client()
    async with await _make_client(es_client) as client:
        # PUT with original casing
        put_response = await client.put(
            f"/city/{city_name}",
            json={"population": population},
        )
        assert put_response.status_code in (200, 201)

        # GET with alternate casing
        get_response = await client.get(f"/city/{alternate_casing}")
        assert get_response.status_code == 200

        data = get_response.json()
        # Should return the original casing
        assert data["city"] == city_name
        assert data["population"] == population


# --- Property 4: Invalid inputs are rejected ---


# Strategies for invalid inputs
negative_population_strategy = st.integers(max_value=-1)
over_max_population_strategy = st.integers(min_value=100_000_000_000)
empty_city_name = st.just("")
# Use spaces only (URL-safe whitespace) for whitespace-only city names
whitespace_only_city_name = st.text(
    alphabet=" ",
    min_size=1,
    max_size=10,
)
# Too-long city names using URL-safe alphabet
too_long_city_name = st.text(
    alphabet=_CITY_NAME_ALPHABET,
    min_size=129,
    max_size=200,
).filter(lambda s: s.strip() != "")


@settings(max_examples=100)
@given(population=negative_population_strategy)
@pytest.mark.asyncio
async def test_invalid_negative_population_rejected(population):
    """Property 4a: Negative population returns 422.

    Feature: sre-city-population-api, Property 4: Invalid inputs are rejected
    **Validates: Requirements 2.4, 2.5, 8.3**
    """
    es_client = _create_notfound_mock_es_client()
    async with await _make_client(es_client) as client:
        response = await client.put(
            "/city/ValidCity",
            json={"population": population},
        )
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data


@settings(max_examples=100)
@given(population=over_max_population_strategy)
@pytest.mark.asyncio
async def test_invalid_over_max_population_rejected(population):
    """Property 4b: Population > max returns 422.

    Feature: sre-city-population-api, Property 4: Invalid inputs are rejected
    **Validates: Requirements 2.4, 2.5, 8.3**
    """
    es_client = _create_notfound_mock_es_client()
    async with await _make_client(es_client) as client:
        response = await client.put(
            "/city/ValidCity",
            json={"population": population},
        )
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data


@settings(max_examples=100)
@given(city_name=whitespace_only_city_name)
@pytest.mark.asyncio
async def test_invalid_whitespace_only_city_rejected(city_name):
    """Property 4c: Whitespace-only city name returns 422.

    Feature: sre-city-population-api, Property 4: Invalid inputs are rejected
    **Validates: Requirements 2.4, 2.5, 8.3**
    """
    es_client = _create_notfound_mock_es_client()
    async with await _make_client(es_client) as client:
        response = await client.put(
            f"/city/{city_name}",
            json={"population": 1000},
        )
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data


@settings(max_examples=100)
@given(city_name=too_long_city_name)
@pytest.mark.asyncio
async def test_invalid_too_long_city_rejected(city_name):
    """Property 4d: City name > 128 chars returns 422.

    Feature: sre-city-population-api, Property 4: Invalid inputs are rejected
    **Validates: Requirements 2.4, 2.5, 8.3**
    """
    es_client = _create_notfound_mock_es_client()
    async with await _make_client(es_client) as client:
        response = await client.put(
            f"/city/{city_name}",
            json={"population": 1000},
        )
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data


# --- Property 5: Non-existent city returns 404 ---


@settings(max_examples=100)
@given(
    city_name=valid_city_name_strategy,
)
@pytest.mark.asyncio
async def test_non_existent_city_returns_404(city_name):
    """Property 5: GET for a city that was never stored returns 404 with detail field.

    Feature: sre-city-population-api, Property 5: Non-existent city returns 404
    **Validates: Requirements 3.2**
    """
    es_client = _create_notfound_mock_es_client()
    async with await _make_client(es_client) as client:
        response = await client.get(f"/city/{city_name}")
        assert response.status_code == 404

        data = response.json()
        assert "detail" in data
        assert isinstance(data["detail"], str)


# --- Property 6: Error responses are safe and well-formed ---

# Patterns that indicate leaked internals
_STACK_TRACE_PATTERN = re.compile(
    r"(Traceback \(most recent call last\)|File \".+\", line \d+|"
    r"at .+:\d+:\d+|\.py:\d+|/usr/|/app/|\\\\app\\\\|C:\\\\)"
)


@settings(max_examples=100)
@given(
    data=st.one_of(
        # Invalid population (negative)
        st.tuples(valid_city_name_strategy, st.integers(max_value=-1)).map(
            lambda t: ("put", t[0], {"population": t[1]})
        ),
        # Invalid population (too large)
        st.tuples(valid_city_name_strategy, st.integers(min_value=100_000_000_000)).map(
            lambda t: ("put", t[0], {"population": t[1]})
        ),
        # Non-existent city GET
        valid_city_name_strategy.map(lambda name: ("get", name, None)),
        # Too long city name
        too_long_city_name.map(lambda name: ("put", name, {"population": 100})),
    ),
)
@pytest.mark.asyncio
async def test_error_responses_are_safe_and_well_formed(data):
    """Property 6: Error responses are JSON with detail <= 500 chars, no stack traces.

    Feature: sre-city-population-api, Property 6: Error responses are safe and well-formed
    **Validates: Requirements 8.1, 8.2**
    """
    method, city_name, body = data
    es_client = _create_notfound_mock_es_client()
    async with await _make_client(es_client) as client:
        if method == "put":
            response = await client.put(f"/city/{city_name}", json=body)
        else:
            response = await client.get(f"/city/{city_name}")

        # Should be an error response (4xx or 5xx)
        assert response.status_code >= 400

        # Must be valid JSON
        response_data = response.json()

        # Must have a detail field
        assert "detail" in response_data
        detail = response_data["detail"]

        # Detail must be a string <= 500 chars
        assert isinstance(detail, str)
        assert len(detail) <= 500

        # Must not contain stack traces or file paths
        assert not _STACK_TRACE_PATTERN.search(detail), (
            f"Detail contains unsafe content: {detail!r}"
        )
