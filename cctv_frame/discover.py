"""Find stations: list still-image cameras from TfL or a local Osiris instance.

Osiris is used as a catalogue only. The frame fetches each chosen feed_url
directly from the agency, so it keeps working when Osiris is off and sends an
honest User-Agent (Osiris's own fetcher spoofs residential IPs; this does not).
"""

from math import asin, cos, radians, sin, sqrt

import requests

from playlist import add_to_playlist, slug

TFL_LIST_URL = "https://api.tfl.gov.uk/Place/Type/JamCam"
USER_AGENT = "cctv-frame/0.3 (private non-commercial display)"
NON_SNAPSHOT_HINTS = ("youtube.com", "youtu.be", "earthcam.com", "skylinewebcams.com",
                      ".m3u8", ".mp4", ".html", "/embed")
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")


def list_tfl(name_filter):
    resp = requests.get(TFL_LIST_URL, timeout=30, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    needle = (name_filter or "").lower()
    for place in resp.json():
        props = {p["key"]: p["value"] for p in place.get("additionalProperties", [])}
        if needle in place.get("commonName", "").lower() and props.get("available") == "true":
            print(f"{place['commonName']}\n    {props.get('imageUrl')}")


def _km(lat1, lng1, lat2, lng2):
    dlat, dlng = radians(lat2 - lat1), radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 6371 * 2 * asin(sqrt(a))


def _snapshot_kind(cam):
    """'jpg' if the feed is a still image the frame can pull, else None."""
    url = (cam.get("feed_url") or "").lower()
    if not url.startswith("http") or cam.get("stream_type") in ("hls", "iframe", "mjpeg"):
        return None
    if any(h in url for h in NON_SNAPSHOT_HINTS):
        return None
    return "jpg" if url.split("?")[0].endswith(IMAGE_EXTS) or cam.get("stream_type") == "jpg" else "jpg?"


def _probe(url):
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": USER_AGENT})
    except requests.RequestException as exc:
        return f"FAIL {type(exc).__name__}"
    if r.ok and r.headers.get("content-type", "").startswith("image/"):
        return "OK"
    return f"FAIL {r.status_code} {r.headers.get('content-type', '')}"


def list_osiris(base_url, region=None, near=None, radius_km=25, limit=30, probe=False,
                save_to=None):
    """Print still-image cameras from Osiris; with save_to, add the [OK] ones as stations."""
    params = {}
    if region:
        params["region"] = region
    elif near:
        params.update(lat=near[0], lng=near[1], radius=radius_km)
    resp = requests.get(base_url.rstrip("/") + "/api/cctv", params=params, timeout=90)
    resp.raise_for_status()
    body = resp.json()
    cams = []
    for cam in body.get("cameras", []):
        kind = _snapshot_kind(cam)
        if not kind:
            continue
        dist = _km(near[0], near[1], cam["lat"], cam["lng"]) if near else None
        if dist is not None and dist > radius_km:
            continue
        cams.append((dist, kind, cam))
    cams.sort(key=lambda t: (t[0] is None, t[0] or 0, t[1] != "jpg"))
    if body.get("pendingRegions"):
        print(f"# still loading in Osiris: {', '.join(body['pendingRegions'])} (re-run shortly)")
    print(f"# {len(cams)} still-image cameras of {body.get('total', '?')} returned")
    keep = []
    for dist, kind, cam in cams[:limit]:
        if probe or save_to:
            kind = _probe(cam["feed_url"])
        where = f"{dist:5.1f} km" if dist is not None else cam.get("country", "")
        print(f"[{kind}] {cam.get('name')} · {cam.get('city', '')} · {cam.get('source')} · {where}\n"
              f"    {cam['feed_url']}")
        if kind == "OK":
            keep.append({
                "id": slug(cam.get("id") or cam.get("name", "cam")),
                "name": cam.get("name", "Camera"),
                "city": cam.get("city", ""),
                "country": cam.get("country", ""),
                "lat": cam["lat"],
                "lng": cam["lng"],
                "image_url": cam["feed_url"],
                "source": cam.get("source", ""),
            })
    if save_to:
        print(f"# added {add_to_playlist(save_to, keep)} station(s) to {save_to}")
