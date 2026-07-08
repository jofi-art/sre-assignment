"""FastAPI application entry point with lifespan handler."""

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.elasticsearch import (
    check_es_health,
    close_es_client,
    ensure_index,
    get_es_client,
)
from app.exceptions import register_exception_handlers
from app.routes import router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown lifecycle.

    Startup:
        - Load settings from environment variables
        - Create Elasticsearch client
        - Verify ES connectivity (exit if unreachable)
        - Ensure the required index exists

    Shutdown:
        - Close the Elasticsearch client connection
    """
    # --- Startup ---
    settings = get_settings()
    app.state.settings = settings

    es_client = get_es_client(settings)
    app.state.es_client = es_client

    # Verify Elasticsearch is reachable
    is_healthy = await check_es_health(es_client, settings.es_timeout)
    if not is_healthy:
        logger.error(
            "Failed to connect to Elasticsearch at %s://%s:%d — exiting.",
            settings.elasticsearch_scheme,
            settings.elasticsearch_host,
            settings.elasticsearch_port,
        )
        await close_es_client(es_client)
        sys.exit(1)

    # Create index if it does not exist
    try:
        await ensure_index(es_client, settings.index_name)
    except Exception as exc:
        logger.error("Failed to ensure Elasticsearch index: %s — exiting.", exc)
        await close_es_client(es_client)
        sys.exit(1)

    yield

    # --- Shutdown ---
    await close_es_client(app.state.es_client)


app = FastAPI(title="City Population API", lifespan=lifespan)

# Register API routes
app.include_router(router)

# Register custom exception handlers
register_exception_handlers(app)
