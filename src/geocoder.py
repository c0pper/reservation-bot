import logging
import os

import httpx

logger = logging.getLogger(__name__)

GEOAPIFY_API_KEY = os.environ.get("GEOAPIFY_API_KEY", "")


async def reverse_geocode(lat: float, lon: float) -> str | None:
    if not GEOAPIFY_API_KEY:
        logger.warning("GEOAPIFY_API_KEY not set — skipping geocode")
        return None

    url = f"https://api.geoapify.com/v1/geocode/reverse?lat={lat}&lon={lon}&apiKey={GEOAPIFY_API_KEY}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            features = data.get("features", [])
            if not features:
                return None
            props = features[0].get("properties", {})
            return props.get("name") or props.get("address_line1")
    except Exception as e:
        logger.exception("Reverse geocode failed for (%f, %f): %s", lat, lon, e)
        return None