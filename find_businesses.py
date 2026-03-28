"""
Module 1: Find HVAC businesses via Google Places API (New)
"""

import requests
import time
from config import GOOGLE_PLACES_API_KEY, NICHE_KEYWORD, TOP_10_METROS


def search_places_in_city(city_info, keyword=None, max_results=20):
    """Search Google Places API for businesses in a given city."""
    keyword = keyword or NICHE_KEYWORD
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_PLACES_API_KEY,
        "X-Goog-FieldMask": (
            "places.displayName,places.formattedAddress,places.websiteUri,"
            "places.nationalPhoneNumber,places.googleMapsUri,places.rating,"
            "places.userRatingCount,places.id"
        ),
    }
    query = f"{keyword} in {city_info['city']}, {city_info['state']}"
    payload = {
        "textQuery": query,
        "maxResultCount": max_results,
        "locationBias": {
            "circle": {
                "center": {"latitude": city_info["lat"], "longitude": city_info["lng"]},
                "radius": 50000.0,
            }
        },
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        results = []
        for place in data.get("places", []):
            results.append({
                "name": place.get("displayName", {}).get("text", "Unknown"),
                "address": place.get("formattedAddress", ""),
                "phone": place.get("nationalPhoneNumber", ""),
                "website": place.get("websiteUri", ""),
                "maps_url": place.get("googleMapsUri", ""),
                "rating": place.get("rating", 0),
                "review_count": place.get("userRatingCount", 0),
                "place_id": place.get("id", ""),
                "city": city_info["city"],
                "state": city_info["state"],
            })
        return results
    except requests.exceptions.RequestException as e:
        print(f"  [ERROR] API call failed for {city_info['city']}: {e}")
        return []


def find_all_businesses(keyword=None, metros=None):
    """Run search across all metros. Returns list of business dicts."""
    metros = metros or TOP_10_METROS
    keyword = keyword or NICHE_KEYWORD
    all_businesses = []

    for i, metro in enumerate(metros, 1):
        print(f"  [{i}/{len(metros)}] Searching {metro['city']}, {metro['state']}...")
        results = search_places_in_city(metro, keyword=keyword)
        # Deduplicate by website URL
        for biz in results:
            if biz["website"] and not any(
                b["website"] == biz["website"] for b in all_businesses
            ):
                all_businesses.append(biz)
        print(f"    Found {len(results)} businesses ({len(all_businesses)} unique total)")
        if i < len(metros):
            time.sleep(0.5)

    print(f"\n  Total unique businesses with websites: {len(all_businesses)}")
    return all_businesses
