"""API route handlers for the City Population API."""

import json

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.elasticsearch import check_es_health
from app.exceptions import CityNotFoundError
from app.models import UpsertCityRequest
from app.repository import get_city, upsert_city

router = APIRouter()


def _validate_city_name(city_name: str) -> str | None:
    """Validate city_name path parameter.

    Returns an error message string if invalid, or None if valid.
    """
    if not city_name or not city_name.strip():
        return "City name must not be empty"
    if len(city_name) > 128:
        return "City name must not exceed 128 characters"
    return None


@router.get("/health")
async def health_check(request: Request) -> JSONResponse:
    """Check service health by verifying Elasticsearch connectivity.

    Returns 200 if ES is reachable within the configured timeout,
    503 otherwise.
    """
    settings = request.app.state.settings
    es_client = request.app.state.es_client

    is_healthy = await check_es_health(es_client, settings.es_timeout)

    if is_healthy:
        return JSONResponse(
            status_code=200,
            content={"status": "ok"},
        )
    else:
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "detail": "Database unreachable"},
        )


@router.put("/city/{city_name}")
async def upsert_city_endpoint(
    city_name: str,
    request: Request,
) -> Response:
    """Create or update a city population record.

    Validates the city name first, then parses and validates the request body.
    Returns 201 for new cities, 200 for updates.
    """
    # Validate city_name before parsing body
    error = _validate_city_name(city_name)
    if error:
        return JSONResponse(
            status_code=422,
            content={"detail": error},
        )

    # Parse and validate request body
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        return JSONResponse(
            status_code=422,
            content={"detail": "Request body is not valid JSON"},
        )

    try:
        city_request = UpsertCityRequest(**body)
    except ValidationError as exc:
        errors = exc.errors()
        if errors:
            first_error = errors[0]
            loc = first_error.get("loc", ())
            msg = first_error.get("msg", "Validation error")
            loc_parts = [str(part) for part in loc]
            if loc_parts:
                detail = f"{' -> '.join(loc_parts)}: {msg}"
            else:
                detail = msg
        else:
            detail = "Validation error"
        return JSONResponse(
            status_code=422,
            content={"detail": detail},
        )

    settings = request.app.state.settings
    es_client = request.app.state.es_client

    record, is_new = await upsert_city(
        client=es_client,
        index=settings.index_name,
        city_name=city_name,
        population=city_request.population,
    )

    status_code = 201 if is_new else 200
    return JSONResponse(
        status_code=status_code,
        content={"city": record["city"], "population": record["population"]},
    )


@router.get("/city/{city_name}")
async def get_city_endpoint(city_name: str, request: Request) -> JSONResponse:
    """Retrieve a city population record by name.

    Performs case-insensitive lookup and returns the original stored casing.
    Raises CityNotFoundError if the city does not exist.
    """
    settings = request.app.state.settings
    es_client = request.app.state.es_client

    result = await get_city(
        client=es_client,
        index=settings.index_name,
        city_name=city_name,
    )

    if result is None:
        raise CityNotFoundError(city_name)

    return JSONResponse(
        status_code=200,
        content={"city": result["city"], "population": result["population"]},
    )
