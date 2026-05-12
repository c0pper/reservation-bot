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


async def forward_geocode(text: str) -> tuple[list[tuple[float, float, str, str, str]], str | None]:
    if not GEOAPIFY_API_KEY:
        logger.warning("GEOAPIFY_API_KEY not set — skipping geocode")
        return [], "api_key"

    url = f"https://api.geoapify.com/v1/geocode/search?text={text}&apiKey={GEOAPIFY_API_KEY}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            features = data.get("features", [])
            if not features:
                return [], "no_results"
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
                city = props.get("city", "")
                postcode = props.get("postcode", "")
                results.append((lat, lon, formatted, city, postcode))
            if not results:
                logger.info("No Campania result for address: %s", text)
                return [], "not_in_campania"
            return results, None
    except Exception as e:
            logger.exception("Forward geocode failed for '%s': %s", text, e)
            return [], "network"


async def get_transit_time(
    lat1: float, lon1: float, lat2: float, lon2: float, mode: str = "bus"
) -> float:
    if not GEOAPIFY_API_KEY:
        logger.warning("⚠️ GEOAPIFY_API_KEY not set — assuming 1 hour transit time ⚠️")
        return 3600.0

    url = (
        f"https://api.geoapify.com/v1/routing?"
        f"waypoints={lat1},{lon1}|{lat2},{lon2}&mode={mode}&apiKey={GEOAPIFY_API_KEY}"
    )
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            features = data.get("features", [])
            if not features:
                logger.warning("⚠️ Routing returned no features — assuming 1 hour transit time ⚠️")
                return 3600.0
            properties = features[0].get("properties", {})
            travel_time = properties.get("time")
            if travel_time is None:
                logger.warning("⚠️ Routing response missing time — assuming 1 hour transit time ⚠️")
                return 3600.0
            return travel_time + 1800
    except Exception as e:
        logger.exception("⚠️ Routing failed for (%f,%f) -> (%f,%f): %s — assuming 1 hour transit time ⚠️", lat1, lon1, lat2, lon2, e)
        return 3600.0