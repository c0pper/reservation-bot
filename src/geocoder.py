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


async def forward_geocode(text: str) -> list[tuple[float, float, str]]:
    if not GEOAPIFY_API_KEY:
        logger.warning("GEOAPIFY_API_KEY not set — skipping geocode")
        return []

    url = f"https://api.geoapify.com/v1/geocode/search?text={text}&apiKey={GEOAPIFY_API_KEY}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            features = data.get("features", [])
            results = []
            for f in features:
                props = f.get("properties", {})
                state = props.get("state") or ""
                if state.lower() != "campania":
                    continue
                lat = props.get("lat")
                lon = props.get("lon")
                if lat is None or lon is None:
                    continue
                formatted = props.get("formatted") or props.get("address_line1") or text
                results.append((lat, lon, formatted))
            if not results:
                logger.info("No Campania result for address: %s", text)
            return results
    except Exception as e:
        logger.exception("Forward geocode failed for '%s': %s", text, e)
        return []