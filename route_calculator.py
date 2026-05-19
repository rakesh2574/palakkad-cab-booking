"""
Route calculator using OpenRouteService API.
Geocodes place names → gets real driving distance & duration.
Falls back to None if API fails (so GPT estimate can be used as backup).
"""

import os
import requests
from functools import lru_cache

ORS_API_KEY = os.getenv(
    "ORS_API_KEY",
    "eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6IjcwNmU2MzJmZGU3NDQ2Y2FiZTNhZGY0YjBlMGJhMDU0IiwiaCI6Im11cm11cjY0In0=",
)

BASE_URL = "https://api.openrouteservice.org"
HEADERS = {"Authorization": ORS_API_KEY, "Content-Type": "application/json"}

# Bias geocoding towards Kerala / South India region
GEOCODE_FOCUS = {"focus.point.lat": 10.85, "focus.point.lon": 76.27}  # Palakkad center
GEOCODE_BOUNDARY = {
    "boundary.rect.min_lat": 8.0,    # Southern tip of Kerala
    "boundary.rect.max_lat": 13.5,   # Up to Bangalore/Chennai
    "boundary.rect.min_lon": 74.5,   # West coast
    "boundary.rect.max_lon": 80.5,   # East to Chennai
}


@lru_cache(maxsize=200)
def geocode(place_name: str) -> tuple | None:
    """
    Convert a place name to (lon, lat) coordinates.
    Uses OpenRouteService Pelias geocoder with South India bias.
    Returns (longitude, latitude) or None if not found.
    """
    try:
        params = {
            "api_key": ORS_API_KEY,
            "text": place_name,
            "size": 1,
            **GEOCODE_FOCUS,
            **GEOCODE_BOUNDARY,
        }
        resp = requests.get(f"{BASE_URL}/geocode/search", params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()

        features = data.get("features", [])
        if not features:
            # Try appending "Kerala India" for better results
            params["text"] = f"{place_name}, Kerala, India"
            resp = requests.get(f"{BASE_URL}/geocode/search", params=params, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            features = data.get("features", [])

        if not features:
            return None

        coords = features[0]["geometry"]["coordinates"]  # [lon, lat]
        return (coords[0], coords[1])
    except Exception as e:
        print(f"Geocode error for '{place_name}': {e}")
        return None


def get_route(from_place: str, to_place: str) -> dict | None:
    """
    Get driving route between two places.

    Returns dict with:
        - distance_km: float (road distance)
        - duration_min: float (driving time in minutes)
        - from_coords: (lon, lat)
        - to_coords: (lon, lat)
        - from_resolved: str (resolved place name from geocoder)
        - to_resolved: str (resolved place name from geocoder)
    Or None if geocoding or routing fails.
    """
    from_coords = geocode(from_place)
    to_coords = geocode(to_place)

    if not from_coords or not to_coords:
        print(f"Geocode failed: from={from_place}({from_coords}) to={to_place}({to_coords})")
        return None

    try:
        body = {
            "coordinates": [list(from_coords), list(to_coords)],
            "instructions": False,
        }
        resp = requests.post(
            f"{BASE_URL}/v2/directions/driving-car",
            json=body,
            headers=HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        segment = data["routes"][0]["summary"]
        distance_km = round(segment["distance"] / 1000, 1)
        duration_min = round(segment["duration"] / 60, 0)

        return {
            "distance_km": distance_km,
            "duration_min": int(duration_min),
            "from_coords": from_coords,
            "to_coords": to_coords,
        }
    except Exception as e:
        print(f"Route error {from_place} → {to_place}: {e}")
        return None


def get_route_with_stops(places: list[str]) -> dict | None:
    """
    Get driving route through multiple stops.
    places: list of place names in order [pickup, stop1, stop2, ..., drop]

    Returns dict with total distance_km and duration_min, plus per-leg breakdown.
    """
    if len(places) < 2:
        return None

    coords = []
    for place in places:
        c = geocode(place)
        if not c:
            print(f"Geocode failed for stop: {place}")
            return None
        coords.append(list(c))

    try:
        body = {"coordinates": coords, "instructions": False}
        resp = requests.post(
            f"{BASE_URL}/v2/directions/driving-car",
            json=body,
            headers=HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        route = data["routes"][0]
        total_distance = round(route["summary"]["distance"] / 1000, 1)
        total_duration = round(route["summary"]["duration"] / 60, 0)

        legs = []
        for i, seg in enumerate(route.get("segments", [])):
            legs.append({
                "from": places[i],
                "to": places[i + 1],
                "distance_km": round(seg["distance"] / 1000, 1),
                "duration_min": int(round(seg["duration"] / 60, 0)),
            })

        return {
            "distance_km": total_distance,
            "duration_min": int(total_duration),
            "legs": legs,
        }
    except Exception as e:
        print(f"Multi-stop route error: {e}")
        return None


# Quick test
if __name__ == "__main__":
    print("Testing Palakkad → Coimbatore Airport...")
    result = get_route("Palakkad", "Coimbatore Airport")
    if result:
        print(f"  Distance: {result['distance_km']} km")
        print(f"  Duration: {result['duration_min']} min")
    else:
        print("  Failed!")

    print("\nTesting Palakkad → Ottapalam...")
    result = get_route("Palakkad", "Ottapalam")
    if result:
        print(f"  Distance: {result['distance_km']} km")
        print(f"  Duration: {result['duration_min']} min")
    else:
        print("  Failed!")
