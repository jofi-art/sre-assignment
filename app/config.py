"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings populated from environment variables.

    Required:
        ELASTICSEARCH_HOST - Elasticsearch hostname
        ELASTICSEARCH_PORT - Elasticsearch port number

    Optional (with defaults):
        ELASTICSEARCH_SCHEME - Connection scheme (default: "http")
        INDEX_NAME - Elasticsearch index name (default: "cities")
        ES_TIMEOUT - Health check timeout in seconds (default: 3)
    """

    elasticsearch_host: str
    elasticsearch_port: int
    elasticsearch_scheme: str = "http"
    index_name: str = "cities"
    es_timeout: int = 3


def get_settings() -> Settings:
    """Load and validate settings from environment variables.

    Raises:
        SystemExit: If required environment variables are missing, logs which
            variable is missing and exits with code 1.
    """
    try:
        return Settings()  # type: ignore[call-arg]
    except Exception as exc:
        import sys

        error_msg = str(exc)
        # Extract the missing field names from the validation error
        missing_vars: list[str] = []
        if hasattr(exc, "errors"):
            for error in exc.errors():  # type: ignore[attr-defined]
                field = error.get("loc", ("unknown",))[-1]
                missing_vars.append(str(field).upper())

        if missing_vars:
            print(
                f"ERROR: Missing required environment variable(s): "
                f"{', '.join(missing_vars)}",
                file=sys.stderr,
            )
        else:
            print(f"ERROR: Configuration failure: {error_msg}", file=sys.stderr)

        sys.exit(1)
