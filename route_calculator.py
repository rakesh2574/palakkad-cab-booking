"""
Route calculator using Google Maps Platform APIs.
Geocodes place names → gets real driving distance & duration.
Falls back to None if API fails (so GPT estimate can be used as backup).

Uses:
  - Google Geocoding API  (place name → lat/lng)
  - Google Directions API (driving distance & duration)
"""

import os
import requests
from functools import lru_cache

GOOGLE_MAPS_API_KEY = os.getenv(
    "GOOGLE_MAPS_API_KEY",
    "AIzaSyCNWwJMq2LSI8MVFh1qOV9Cy5XsUaJQP6s",
)

# Bias geocoding towards Kerala / South India region
GEOCODE_BOUNDS = "8.0,74.5|13.5,80.5"  # SW lat,lng | NE lat,lng
GEOCODE_REGION = "in"  # Country bias: India


@lru_cache(maxsize=200)
def geocode(place_name: str) -> tuple | None:
    """
    Convert a place name to (lat, lng) coordinates using Google Geocoding API.
    Returns (latitude, longitude) or None if not found.
    """
    try:
        params = {
            "address": place_name,
            "key": GOOGLE_MAPS_API_KEY,
            "bounds": GEOCODE_BOUNDS,
            "region": GEOCODE_REGION,
        }
        resp = requests.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params=params,
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != "OK" or not data.get("results"):
            print(f"Geocode: no results for '{place_name}' — status={data.get('status')}")
            return None

        location = data["results"][0]["geometry"]["location"]
        resolved_name = data["results"][0].get("formatted_address", place_name)
        print(f"📍 Geocoded '{place_name}' → {resolved_name} ({location['lat']}, {location['lng']})")
        return (location["lat"], location["lng"])

    except Exception as e:
        print(f"Geocode error for '{place_name}': {e}")
        return None


def get_route(from_place: str, to_place: str) -> dict | None:
    """
    Get driving route between two places using Google Directions API.

    Returns dict with:
        - distance_km: float (road distance)
        - duration_min: int (driving time in minutes)
        - from_coords: (lat, lng)
        - to_coords: (lat, lng)
    Or None if geocoding or routing fails.
    """
    from_coords = geocode(from_place)
    to_coords = geocode(to_place)

    if not from_coords or not to_coords:
        print(f"Geocode failed: from={from_place}({from_coords}) to={to_place}({to_coords})")
        return None

    try:
        params = {
            "origin": f"{from_coords[0]},{from_coords[1]}",
            "destination": f"{to_coords[0]},{to_coords[1]}",
            "mode": "driving",
            "key": GOOGLE_MAPS_API_KEY,
        }
        resp = requests.get(
            "https://maps.googleapis.com/maps/api/directions/json",
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != "OK" or not data.get("routes"):
            print(f"Directions API: no route for {from_place} → {to_place} — status={data.get('status')}")
            return None

        leg = data["routes"][0]["legs"][0]
        distance_km = round(leg["distance"]["value"] / 1000, 1)
        duration_min = round(leg["duration"]["value"] / 60)

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
    Get driving route through multiple stops using Google Directions API.
    places: list of place names in order [pickup, stop1, stop2, ..., drop]

    Returns dict with total distance_km and duration_min, plus per-leg breakdown.
    """
    if len(places) < 2:
        return None

    # Geocode all places first
    coords = []
    for place in places:
        c = geocode(place)
        if not c:
            print(f"Geocode failed for stop: {place}")
            return None
        coords.append(c)

    try:
        # Google Directions supports waypoints between origin and destination
        origin = f"{coords[0][0]},{coords[0][1]}"
        destination = f"{coords[-1][0]},{coords[-1][1]}"

        # Intermediate stops as waypoints
        waypoints = None
        if len(coords) > 2:
            wp_list = [f"{c[0]},{c[1]}" for c in coords[1:-1]]
            waypoints = "|".join(wp_list)

        params = {
            "origin": origin,
            "destination": destination,
            "mode": "driving",
            "key": GOOGLE_MAPS_API_KEY,
        }
        if waypoints:
            params["waypoints"] = waypoints

        resp = requests.get(
            "https://maps.googleapis.com/maps/api/directions/json",
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != "OK" or not data.get("routes"):
            print(f"Multi-stop Directions API failed — status={data.get('status')}")
            return None

        route = data["routes"][0]

        # Sum up all legs
        total_distance = 0
        total_duration = 0
        legs = []

        for i, leg in enumerate(route["legs"]):
            leg_dist = round(leg["distance"]["value"] / 1000, 1)
            leg_dur = int(round(leg["duration"]["value"] / 60))
            total_distance += leg["distance"]["value"]
            total_duration += leg["duration"]["value"]
            legs.append({
                "from": places[i],
                "to": places[i + 1],
                "distance_km": leg_dist,
                "duration_min": leg_dur,
            })

        return {
            "distance_km": round(total_distance / 1000, 1),
            "duration_min": int(round(total_duration / 60)),
            "legs": legs,
        }
    except Exception as e:
        print(f"Multi-stop route error: {e}")
        return None


# Quick test
if __name__ == "__main__":
    print("Testing Koppam, Palakkad, Kerala → Kakkanad, Ernakulam, Kerala...")
    result = get_route("Koppam, Palakkad, Kerala, India", "Kakkanad, Ernakulam, Kerala, India")
    if result:
        print(f"  Distance: {result['distance_km']} km")
        print(f"  Duration: {result['duration_min']} min")
    else:
        print("  Failed!")

    print("\nTesting Palakkad → Thrissur...")
    result = get_route("Palakkad, Kerala, India", "Thrissur, Kerala, India")
    if result:
        print(f"  Distance: {result['distance_km']} km")
        print(f"  Duration: {result['duration_min']} min")
    else:
        print("  Failed!")

    print("\nTesting multi-stop: Palakkad → Thrissur → Kochi...")
    result = get_route_with_stops([
        "Palakkad, Kerala, India",
        "Thrissur, Kerala, India",
        "Kochi, Kerala, India",
    ])
    if result:
        print(f"  Total: {result['distance_km']} km, {result['duration_min']} min")
        for leg in result["legs"]:
            print(f"    {leg['from']} → {leg['to']}: {leg['distance_km']} km, {leg['duration_min']} min")
    else:
        print("  Failed!")
