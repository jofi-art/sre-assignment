"""Elasticsearch client lifecycle management."""

from elasticsearch import AsyncElasticsearch

from app.config import Settings


def get_es_client(settings: Settings) -> AsyncElasticsearch:
    """Create and return an AsyncElasticsearch client instance.

    Args:
        settings: Application settings containing ES connection details.

    Returns:
        A configured AsyncElasticsearch client.
    """
    return AsyncElasticsearch(
        hosts=[
            {
                "scheme": settings.elasticsearch_scheme,
                "host": settings.elasticsearch_host,
                "port": settings.elasticsearch_port,
            }
        ]
    )


async def check_es_health(client: AsyncElasticsearch, timeout: int) -> bool:
    """Check if Elasticsearch is reachable within the given timeout.

    Args:
        client: The AsyncElasticsearch client instance.
        timeout: Maximum seconds to wait for a response.

    Returns:
        True if ES responds to a ping within the timeout, False otherwise.
    """
    try:
        return await client.ping(request_timeout=timeout)
    except Exception:
        return False


async def ensure_index(client: AsyncElasticsearch, index_name: str) -> None:
    """Create the cities index with the required mapping if it does not exist.

    If the index already exists, it is reused without modification.

    Args:
        client: The AsyncElasticsearch client instance.
        index_name: Name of the Elasticsearch index to create or verify.
    """
    exists = await client.indices.exists(index=index_name)
    if not exists:
        await client.indices.create(
            index=index_name,
            body={
                "settings": {
                    "number_of_shards": 1,
                    "number_of_replicas": 0,
                },
                "mappings": {
                    "properties": {
                        "city_display_name": {"type": "keyword"},
                        "population": {"type": "long"},
                    }
                },
            },
        )


async def close_es_client(client: AsyncElasticsearch) -> None:
    """Gracefully close the Elasticsearch connection.

    Args:
        client: The AsyncElasticsearch client instance to close.
    """
    await client.close()
