"""Pydantic request/response models for the City Population API."""

from pydantic import BaseModel, Field


class UpsertCityRequest(BaseModel):
    """Request body for PUT /city/{city_name}."""

    population: int = Field(ge=0, le=99_999_999_999)


class CityResponse(BaseModel):
    """Response body for successful city operations."""

    city: str
    population: int


class ErrorResponse(BaseModel):
    """Standard error response format."""

    detail: str = Field(max_length=500)


class HealthResponse(BaseModel):
    """Response body for GET /health."""

    status: str
    detail: str | None = None
