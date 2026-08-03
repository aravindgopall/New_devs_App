import json
import redis.asyncio as redis
from typing import Dict, Any
import os

# Initialize Redis client (typically configured centrally).
redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))

CACHE_TTL = 300


def revenue_cache_key(property_id: str, tenant_id: str) -> str:
    return f"revenue:tenant:{tenant_id}:property:{property_id}"


async def get_revenue_summary(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Fetches revenue summary, utilizing caching to improve performance.
    """
    if not tenant_id:
        raise ValueError("tenant_id is required to read revenue data")

    cache_key = revenue_cache_key(property_id, tenant_id)

    cached = await redis_client.get(cache_key)
    if cached:
        return json.loads(cached)

    # Revenue calculation is delegated to the reservation service.
    from app.services.reservations import calculate_total_revenue

    result = await calculate_total_revenue(property_id, tenant_id)

    await redis_client.setex(cache_key, CACHE_TTL, json.dumps(result))

    return result
