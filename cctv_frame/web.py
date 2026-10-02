#!/usr/bin/env python3
"""
Visual radio as a web page.

    python web.py                 # then open http://localhost:8000
    python web.py --open          # same, and open it in your default browser
    python web.py --host 0.0.0.0  # also reachable from a phone on the same Wi-Fi

The browser draws the UI (stations, static, station ID, sidebar). This server:
- fetches snapshot cameras, keeps a last-good copy per station and renders
  pixel mode (browsers can't read the pixels of another site's image);
- relays live HLS video streams (/api/hls/...) so the page can play them and
  restyle the frames into pixel art (same reason: pixels need same-origin);
- logs tune/hold/style events to cache/events.jsonl for the prototype tests.

Only stations in playlist.json are fetched. The HLS relay only follows hosts
that the station's own stream URL or its playlists point to; it is not an
open proxy.
"""

import argparse
import base64
import io
import json
import logging
import re
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urljoin, urlparse, urlsplit

import requests
from PIL import Image

from frame import (CACHE_DIR, CAM_CACHE, HERE, PLAYLIST_PATH, USER_AGENT, fetch_image,
                   load_config)
from pixelate import DEFAULTS as PIXEL_DEFAULTS, PALETTES, pixelate
from playlist import cam_phase, load_playlist

WEB_DIR = HERE / "web"
EVENTS_PATH = CACHE_DIR / "events.jsonl"
BACKOFF_SECONDS = (5, 60, 600)  # wait after 1st, 2nd, 3rd+ consecutive failure
MAX_EVENT_BYTES = 2048
STREAM_TYPES = ("hls", "youtube", "iframe")
URI_ATTR = re.compile(r'URI="([^"]+)"')

log = logging.getLogger("cctv_frame.web")


class Stations:
    """Per-station fetch-on-demand with a disk cache and failure backoff."""

    def __init__(self, cfg, cams):
        self.cfg = cfg
        self.cams = {c["id"]: c for c in cams}
        self.order = [c["id"] for c in cams]
        self.locks = {cid: threading.Lock() for cid in self.cams}
        self.images = {}       # id -> (fetched_at, PIL image, jpeg bytes)
        self.fails = {}        # id -> (consecutive failures, last failure time)
        self.pixel_cache = {}  # (id, fetched_at, palette) -> png bytes

    def _from_disk(self, cid):
        path = CAM_CACHE / f"{cid}.jpg"
        try:
            data = path.read_bytes()
            img = Image.open(io.BytesIO(data))
            img.load()
            return path.stat().st_mtime, img.convert("RGB"), data
        except (OSError, ValueError):
            return None

    def image(self, cid):
        """Latest image for a station, fetching if stale. None if nothing to show."""
        with self.locks[cid]:
            have = self.images.get(cid) or self._from_disk(cid)
            now = time.time()
            if have and now - have[0] < self.cfg["interval_seconds"]:
                return have
            n, at = self.fails.get(cid, (0, 0))
            if n and now - at < BACKOFF_SECONDS[min(n, len(BACKOFF_SECONDS)) - 1]:
                return have  # don't hammer a failing feed
            cam = self.cams[cid]
            if not cam.get("image_url"):
                return have  # live-stream-only station
            try:
                img = fetch_image(cam["image_url"], self.cfg["timeout_seconds"])
            except (requests.RequestException, OSError) as exc:
                self.fails[cid] = (n + 1, now)
                log.warning("%s: fetch failed (%s)", cam["name"], exc)
                if have:
                    self.images[cid] = have
                return have
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=90)
            data = buf.getvalue()
            tmp = CAM_CACHE / f"{cid}.tmp.jpg"
            tmp.write_bytes(data)
            tmp.replace(CAM_CACHE / f"{cid}.jpg")
            self.fails.pop(cid, None)
            self.images[cid] = (now, img, data)
            return self.images[cid]

    def offline(self, cid):
        n, at = self.fails.get(cid, (0, 0))
        if not n or time.time() - at > 600:
            return False
        return n >= 2 or (cid not in self.images and not (CAM_CACHE / f"{cid}.jpg").exists())

    def pixel_png(self, cid, fetched_at, img, ph=None):
        """Small pixel-art PNG; the browser upscales it with crisp integer scaling.
        `ph` is the day/night phase the page is showing; computed here if absent."""
        if ph not in ("day", "dusk", "night"):
            ph = cam_phase(self.cams[cid], datetime.now(timezone.utc))
        palette = self.cfg["pixel"]["night_palette"] if ph == "night" else None
        key = (cid, fetched_at, palette)
        if key not in self.pixel_cache:
            settings = {k: v for k, v in self.cfg["pixel"].items() if k != "night_palette"}
            if palette:
                settings["palette"] = palette
            buf = io.BytesIO()
            pixelate(img, settings).save(buf, "PNG")
            self.pixel_cache = {k: v for k, v in self.pixel_cache.items() if k[0] != cid}
            self.pixel_cache[key] = buf.getvalue()
        return self.pixel_cache[key]


def _b64e(s):
    return base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")


def _b64d(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4)).decode()


class HlsRelay:
    """Relay a station's HLS stream through this server, rewriting playlists.

    Every URI in a playlist is rewritten to /api/hls/<station>/<base64 url>.
    Only hosts that the station's stream URL (or its own playlists) named are
    followed, so the relay can't be pointed at arbitrary sites.
    """

    def __init__(self, cams, timeout):
        self.timeout = timeout
        self.streams = {c["id"]: c["stream_url"] for c in cams
                        if c.get("stream_type") == "hls" and c.get("stream_url")}
        self.allowed = {cid: {urlsplit(u).netloc} for cid, u in self.streams.items()}
        self.lock = threading.Lock()

    def _proxied(self, cid, url):
        with self.lock:
            self.allowed[cid].add(urlsplit(url).netloc)
        return f"/api/hls/{cid}/{_b64e(url)}"

    def rewrite(self, cid, text, base):
        out = []
        for line in text.splitlines():
            s = line.strip()
            if not s:
                out.append(line)
            elif s.startswith("#"):
                out.append(URI_ATTR.sub(
                    lambda m: f'URI="{self._proxied(cid, urljoin(base, m.group(1)))}"', line))
            else:
                out.append(self._proxied(cid, urljoin(base, s)))
        return "\n".join(out) + "\n"

    def resolve(self, cid, token):
        """Upstream URL for a request, or None if not allowed."""
        if cid not in self.streams:
            return None
        if token == "master":
            return self.streams[cid]
        try:
            url = _b64d(token)
        except (ValueError, UnicodeDecodeError):
            return None
        with self.lock:
            ok = urlsplit(url).scheme in ("http", "https") and urlsplit(url).netloc in self.allowed[cid]
        return url if ok else None


def make_handler(cfg, stations, relay):
    public_cfg = {k: cfg[k] for k in ("style", "rotate_seconds", "interval_seconds",
                                      "station_id_seconds", "static_seconds",
                                      "sidebar_timeout_seconds", "image_scale",
                                      "brightness", "prototype") if k in cfg}
    # Pixel settings for live video, which the page pixelates itself.
    px = {**PIXEL_DEFAULTS, **cfg["pixel"]}
    public_cfg["pixel"] = {
        "width": px["width"], "dither": px["dither"], "dither_strength": px["dither_strength"],
        "contrast": px["contrast"], "saturation": px["saturation"],
        "palette": PALETTES.get(px["palette"], PALETTES["city16"]),
        "night_palette": PALETTES.get(px["night_palette"], PALETTES["night16"]),
    }

    class Handler(BaseHTTPRequestHandler):
        server_version = "VisualRadio/0.1"

        def log_message(self, fmt, *args):
            log.debug("%s " + fmt, self.address_string(), *args)

        def _send(self, code, body, ctype, extra=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code=200):
            self._send(code, json.dumps(obj).encode(), "application/json")

        def do_GET(self):
            url = urlparse(self.path)
            if url.path in ("/", "/index.html"):
                return self._send(200, (WEB_DIR / "index.html").read_bytes(),
                                  "text/html; charset=utf-8")
            if url.path.startswith("/vendor/"):
                name = url.path.rsplit("/", 1)[-1]
                path = WEB_DIR / "vendor" / name
                if name.endswith(".js") and path.is_file():
                    return self._send(200, path.read_bytes(), "text/javascript")
                return self._json({"error": "not found"}, 404)
            if url.path == "/api/stations":
                return self._json({"config": public_cfg,
                                   "stations": [self._station(c) for c in stations.order]})
            if url.path.startswith("/api/hls/"):
                parts = url.path.split("/")
                if len(parts) != 5:
                    return self._json({"error": "not found"}, 404)
                return self._relay(parts[3], parts[4])
            if url.path.startswith("/api/frame/"):
                cid = url.path.rsplit("/", 1)[-1]
                if cid not in stations.cams:
                    return self._json({"error": "unknown station"}, 404)
                got = stations.image(cid)
                if got is None:
                    return self._json({"error": "station offline"}, 503)
                fetched_at, img, data = got
                extra = {"X-Fetched-At": str(int(fetched_at))}
                q = parse_qs(url.query)
                if q.get("style", ["real"])[0] == "pixel":
                    png = stations.pixel_png(cid, fetched_at, img, q.get("phase", [None])[0])
                    return self._send(200, png, "image/png", extra)
                return self._send(200, data, "image/jpeg", extra)
            self._json({"error": "not found"}, 404)

        def _station(self, cid):
            cam = stations.cams[cid]
            out = {k: cam.get(k) for k in ("id", "name", "city", "country", "lat", "lng",
                                           "tz", "source")}
            out["offline"] = stations.offline(cid) if cam.get("image_url") else False
            out["has_image"] = bool(cam.get("image_url"))
            kind = cam.get("stream_type")
            if kind in STREAM_TYPES and cam.get("stream_url"):
                # HLS goes through the relay; embedded players load directly.
                out["stream"] = {"type": kind} if kind == "hls" else \
                    {"type": kind, "url": cam["stream_url"]}
            return out

        def _relay(self, cid, token):
            upstream = relay.resolve(cid, token)
            if upstream is None:
                return self._json({"error": "not allowed"}, 403)
            headers = {"User-Agent": USER_AGENT}
            if self.headers.get("Range"):
                headers["Range"] = self.headers["Range"]
            try:
                r = requests.get(upstream, headers=headers, timeout=relay.timeout, stream=True)
            except requests.RequestException as exc:
                log.warning("hls %s: %s", cid, exc)
                return self._json({"error": "upstream unreachable"}, 502)
            with r:
                ctype = r.headers.get("Content-Type", "application/octet-stream")
                is_playlist = "mpegurl" in ctype.lower() or urlsplit(r.url).path.endswith(".m3u8")
                if r.status_code >= 400:
                    return self._json({"error": f"upstream {r.status_code}"}, 502)
                if is_playlist:
                    text = r.content.decode("utf-8", "replace")
                    body = relay.rewrite(cid, text, r.url).encode()
                    return self._send(200, body, "application/vnd.apple.mpegurl")
                self.send_response(r.status_code)
                self.send_header("Content-Type", ctype)
                for h in ("Content-Length", "Content-Range", "Accept-Ranges"):
                    if r.headers.get(h):
                        self.send_header(h, r.headers[h])
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                try:
                    for chunk in r.iter_content(64 * 1024):
                        self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # the player moved on (tuned away or seeked)

        def do_POST(self):
            if urlparse(self.path).path != "/api/event":
                return self._json({"error": "not found"}, 404)
            length = int(self.headers.get("Content-Length") or 0)
            if not 0 < length <= MAX_EVENT_BYTES:
                return self._json({"error": "bad size"}, 400)
            try:
                event = json.loads(self.rfile.read(length))
                if not isinstance(event, dict):
                    raise ValueError
            except ValueError:
                return self._json({"error": "bad json"}, 400)
            event["ts"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            with open(EVENTS_PATH, "a") as f:
                f.write(json.dumps(event) + "\n")
            self._json({"ok": True})

    return Handler


def main():
    parser = argparse.ArgumentParser(description="Serve the visual radio as a web page.")
    parser.add_argument("--host", default="127.0.0.1",
                        help="127.0.0.1 = this computer only; 0.0.0.0 = whole local network")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--open", action="store_true", help="open the page in the default browser")
    parser.add_argument("--config", default=str(HERE / "config.json"))
    parser.add_argument("--playlist", default=str(PLAYLIST_PATH))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    CACHE_DIR.mkdir(exist_ok=True)
    CAM_CACHE.mkdir(exist_ok=True)
    cfg = load_config(args.config)
    cams = load_playlist(args.playlist, cfg)
    stations = Stations(cfg, cams)
    relay = HlsRelay(cams, cfg["timeout_seconds"])
    server = ThreadingHTTPServer((args.host, args.port), make_handler(cfg, stations, relay))
    shown = "localhost" if args.host in ("127.0.0.1", "0.0.0.0") else args.host
    url = f"http://{shown}:{args.port}"
    print(f"Visual radio on {url}  (Ctrl+C to stop)")
    if args.open:
        import webbrowser
        threading.Timer(0.5, webbrowser.open, (url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
