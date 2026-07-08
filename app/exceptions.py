"""Custom exception classes and FastAPI exception handlers."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

MAX_DETAIL_LENGTH = 500


def _truncate_detail(detail: str) -> str:
    """Truncate detail message to MAX_DETAIL_LENGTH characters."""
    if len(detail) > MAX_DETAIL_LENGTH:
        return detail[:MAX_DETAIL_LENGTH]
    return detail


# --- Custom Exception Classes ---


class CityNotFoundError(Exception):
    """Raised when a requested city does not exist in the database."""

    def __init__(self, city_name: str) -> None:
        self.city_name = city_name
        super().__init__(f"City '{city_name}' not found")


class DatabaseUnavailableError(Exception):
    """Raised when the database (Elasticsearch) is unreachable."""

    def __init__(self, detail: str = "Database unavailable") -> None:
        self.detail = detail
        super().__init__(detail)


# --- Exception Handlers ---


async def city_not_found_handler(
    request: Request, exc: CityNotFoundError
) -> JSONResponse:
    """Handle CityNotFoundError → 404 response."""
    return JSONResponse(
        status_code=404,
        content={"detail": _truncate_detail(str(exc))},
    )


async def database_unavailable_handler(
    request: Request, exc: DatabaseUnavailableError
) -> JSONResponse:
    """Handle DatabaseUnavailableError → 503 response."""
    return JSONResponse(
        status_code=503,
        content={"detail": _truncate_detail(exc.detail)},
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle RequestValidationError → 422 response with custom format."""
    errors = exc.errors()
    if errors:
        # Build a human-readable message from the first validation error
        first_error = errors[0]
        loc = first_error.get("loc", ())
        msg = first_error.get("msg", "Validation error")
        # Format location as a readable path (skip 'body' prefix for cleaner messages)
        loc_parts = [str(part) for part in loc if part != "body"]
        if loc_parts:
            detail = f"{' -> '.join(loc_parts)}: {msg}"
        else:
            detail = msg
    else:
        detail = "Validation error"

    return JSONResponse(
        status_code=422,
        content={"detail": _truncate_detail(detail)},
    )


async def generic_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Handle unhandled exceptions → 500 response.

    Logs the full traceback server-side but returns only a generic
    message to the client. Does NOT expose stack traces, file paths,
    or internal identifiers.
    """
    logger.exception("Unhandled exception during request processing")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all custom exception handlers on the FastAPI app."""
    app.add_exception_handler(CityNotFoundError, city_not_found_handler)  # type: ignore[arg-type]
    app.add_exception_handler(DatabaseUnavailableError, database_unavailable_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, generic_exception_handler)  # type: ignore[arg-type]
