"""
HVAC Lead Audit Engine — Configuration
========================================
Setup:
  1. Get a Google Places API key: https://console.cloud.google.com/apis/credentials
     - Enable "Places API (New)" in your project
     - Free tier gives $200/month credit (~1,000 searches)
  2. Set as environment variable: export GOOGLE_PLACES_API_KEY="your-key"
     Or paste directly below (not recommended for Git).
"""

import os

GOOGLE_PLACES_API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY", "")

NICHE_KEYWORD = "HVAC contractor"

# Expandable to 15+ niches — just swap keyword and re-run
ALTERNATE_NICHES = [
    "pest control",
    "water damage restoration",
    "auto glass repair",
    "garage door repair",
    "roofing contractor",
    "plumbing contractor",
    "electrician",
    "locksmith",
    "tree service",
    "junk removal",
]

TOP_10_METROS = [
    {"city": "New York", "state": "NY", "lat": 40.7128, "lng": -74.0060},
    {"city": "Los Angeles", "state": "CA", "lat": 34.0522, "lng": -118.2437},
    {"city": "Chicago", "state": "IL", "lat": 41.8781, "lng": -87.6298},
    {"city": "Houston", "state": "TX", "lat": 29.7604, "lng": -95.3698},
    {"city": "Phoenix", "state": "AZ", "lat": 33.4484, "lng": -112.0740},
    {"city": "Philadelphia", "state": "PA", "lat": 39.9526, "lng": -75.1652},
    {"city": "San Antonio", "state": "TX", "lat": 29.4241, "lng": -98.4936},
    {"city": "San Diego", "state": "CA", "lat": 32.7157, "lng": -117.1611},
    {"city": "Dallas", "state": "TX", "lat": 32.7767, "lng": -96.7970},
    {"city": "Atlanta", "state": "GA", "lat": 33.7490, "lng": -84.3880},
]

# Audit scoring weights — higher = worse for them = better lead for you
# Max possible: 130. Sweet spot targets: 50-100
SCORING = {
    "no_ssl":               10,
    "slow_load":            15,   # >3 seconds
    "no_phone_visible":     20,
    "no_click_to_call":     15,
    "no_contact_form":      10,
    "no_analytics":         10,
    "no_gtm":                5,
    "no_meta_description":   5,
    "no_h1":                 5,
    "homepage_as_landing":  15,
    "no_schema_markup":      5,
    "no_viewport_meta":     10,
    "no_reviews_on_site":    5,
}
