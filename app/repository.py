"""Data access layer for Elasticsearch CRUD operations on city records."""

from elasticsearch import AsyncElasticsearch, NotFoundError


async def upsert_city(
    client: AsyncElasticsearch,
    index: str,
    city_name: str,
    population: int,
) -> tuple[dict, bool]:
    """Store a city population record in Elasticsearch.

    Uses the lowercased city name as the document ``_id`` for
    case-insensitive deduplication.  The original casing is preserved in the
    ``city_display_name`` field.  The write is confirmed via
    ``refresh="wait_for"`` before returning.

    Args:
        client: The AsyncElasticsearch client instance.
        index: Name of the Elasticsearch index.
        city_name: City name (any casing).
        population: Non-negative integer population value.

    Returns:
        A tuple of (record_dict, is_new) where record_dict contains ``city``
        (display name) and ``population``, and is_new is True when the
        document was newly created.
    """
    doc_id = city_name.lower()

    response = await client.index(
        index=index,
        id=doc_id,
        document={
            "city_display_name": city_name,
            "population": population,
        },
        refresh="wait_for",
    )

    is_new = response["result"] == "created"

    record = {
        "city": city_name,
        "population": population,
    }

    return record, is_new


async def get_city(
    client: AsyncElasticsearch,
    index: str,
    city_name: str,
) -> dict | None:
    """Retrieve a city population record from Elasticsearch.

    Looks up the document using the lowercased city name as ``_id``.

    Args:
        client: The AsyncElasticsearch client instance.
        index: Name of the Elasticsearch index.
        city_name: City name to look up (any casing).

    Returns:
        A dict with ``city`` (original display name) and ``population``,
        or None if the city is not found.
    """
    doc_id = city_name.lower()

    try:
        response = await client.get(index=index, id=doc_id)
    except NotFoundError:
        return None

    source = response["_source"]
    return {
        "city": source["city_display_name"],
        "population": source["population"],
    }
