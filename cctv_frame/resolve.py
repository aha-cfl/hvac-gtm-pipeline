"""
Look up a station's current stream URL when it plays.

Many CCTV stream URLs (Seoul's included) carry session tokens that expire, so
a hard-coded URL works for a few hours and then dies. A station can instead be
stored as a *place*, and its URL is looked up from a directory when it plays
and looked up again whenever it stops working:

    "resolve": {"via": "osiris", "near": [37.5721, 127.0235], "name": "Cheonggyecheon"}
        Ask a running Osiris instance (which reads OpenCCTV, Seoul TOPIS and
        others) for live HLS cameras near that point.

    "resolve": {"via": "its", "near": [37.48, 127.03], "road": "its"}
        Ask Korea's national ITS open API (expressways "ex" / national roads
        "its"; not Seoul city streets). Needs ITS_API_KEY in the environment.

The camera whose name contains `name` wins (within `max_m`, default 1500 m);
otherwise the nearest live camera within 400 m. A station's `stream_url`, if
any, is the fallback when the lookup fails.
"""

import logging
import math
import os
import threading
import time

import requests

log = logging.getLogger("cctv_frame.resolve")

TTL_SECONDS = 600            # re-use a looked-up URL this long unless it fails first
ITS_URL = "https://openapi.its.go.kr:9443/cctvInfo"


def _meters(lat1, lng1, lat2, lng2):
    x = math.radians(lng2 - lng1) * math.cos(math.radians((lat1 + lat2) / 2))
    y = math.radians(lat2 - lat1)
    return 6371000 * math.hypot(x, y)


def _rows_with(obj, key):
    """All dicts anywhere in a JSON tree that have `key` (API shapes vary)."""
    if isinstance(obj, dict):
        if key in obj:
            yield obj
        for v in obj.values():
            yield from _rows_with(v, key)
    elif isinstance(obj, list):
        for v in obj:
            yield from _rows_with(v, key)


def pick(candidates, spec):
    """candidates: [(name, lat, lng, url)] -> best url or None."""
    lat, lng = spec["near"]
    hints = spec.get("name") or []
    hints = [hints] if isinstance(hints, str) else hints
    scored = []
    for name, clat, clng, url in candidates:
        d = _meters(lat, lng, clat, clng)
        named = any(h.lower() in (name or "").lower() for h in hints)
        if (named and d <= spec.get("max_m", 1500)) or d <= spec.get("near_m", 400):
            scored.append((not named, d, url))
    return min(scored)[2] if scored else None


class Resolver:
    def __init__(self, cams, osiris_url, timeout):
        self.osiris_url = osiris_url.rstrip("/")
        self.timeout = timeout
        self.specs = {c["id"]: c["resolve"] for c in cams if isinstance(c.get("resolve"), dict)}
        self.fallback = {c["id"]: c["stream_url"] for c in cams
                         if c.get("stream_type") == "hls" and c.get("stream_url")}
        self.cache = {}  # id -> (url, looked_up_at)
        self.last = {}   # id -> last URL logged
        self.lock = threading.Lock()

    def has(self, cid):
        return cid in self.specs or cid in self.fallback

    def url(self, cid):
        """Current stream URL for a station (cached), or None."""
        with self.lock:
            hit = self.cache.get(cid)
        if hit and time.time() - hit[1] < TTL_SECONDS:
            return hit[0]
        if cid in self.specs:
            try:
                found = self._lookup(self.specs[cid])
            except (requests.RequestException, ValueError, KeyError, RuntimeError) as exc:
                log.warning("%s: lookup failed (%s)", cid, exc)
                found = None
            if found:
                with self.lock:
                    self.cache[cid] = (found, time.time())
                if self.last.get(cid) != found:
                    log.info("%s: stream -> %s", cid, found[:100])
                    self.last[cid] = found
                return found
        return self.fallback.get(cid) or (hit[0] if hit else None)

    def invalidate(self, cid):
        """The URL stopped working (expired token, camera moved): look it up again next time."""
        with self.lock:
            self.cache.pop(cid, None)

    def _lookup(self, spec):
        via = spec.get("via")
        if via == "osiris":
            return pick(self._osiris(spec), spec)
        if via == "its":
            return pick(self._its(spec), spec)
        raise ValueError(f"unknown resolver {via!r}")

    def _osiris(self, spec):
        lat, lng = spec["near"]
        r = requests.get(f"{self.osiris_url}/api/cctv", params={"lat": lat, "lng": lng, "radius": 3},
                         timeout=90)
        r.raise_for_status()
        return [(c.get("name", ""), c["lat"], c["lng"], c["stream_url"])
                for c in r.json().get("cameras", [])
                if c.get("stream_type") == "hls" and str(c.get("stream_url", "")).startswith("http")]

    def _its(self, spec):
        key = os.environ.get("ITS_API_KEY")
        if not key:
            raise RuntimeError("set ITS_API_KEY (from https://www.its.go.kr/opendata)")
        lat, lng = spec["near"]
        d = 0.02
        r = requests.get(ITS_URL, timeout=self.timeout, params={
            "apiKey": key, "type": spec.get("road", "its"), "cctvType": 4,
            "minX": lng - d, "maxX": lng + d, "minY": lat - d, "maxY": lat + d, "getType": "json"})
        r.raise_for_status()
        return [(row.get("cctvname", ""), float(row["coordy"]), float(row["coordx"]), row["cctvurl"])
                for row in _rows_with(r.json(), "cctvurl")
                if str(row.get("cctvurl", "")).startswith("http")]
