#!/usr/bin/env python3
"""
CCTV frame — one public traffic camera, fullscreen on black glass.

Two display styles:
    pixel  Aseprite-style sprite art (limited palette, crisp square pixels)
    real   the camera image as-is

Fetches the camera JPEG on a timer and keeps a last-good copy on disk so a
dead feed or a power cut never leaves the screen blank.

Usage:
    python frame.py                     # fullscreen; P/Space toggles style, Esc quits
    python frame.py --style real        # force a style for this run
    python frame.py --once              # fetch + render one frame to cache/, no GUI
    python frame.py --preview photo.jpg # real vs pixel side by side -> cache/preview.png
    python frame.py --list-tfl ABC      # list TfL JamCams whose name contains "ABC"
    python frame.py --list-osiris --near 37.57,126.98 --probe   # cameras from a local Osiris
"""

import argparse
import io
import json
import logging
import os
import sys
import threading
from pathlib import Path

import requests
from PIL import Image, ImageEnhance, ImageOps

from pixelate import pixelate

HERE = Path(__file__).resolve().parent
CACHE_DIR = HERE / "cache"
RAW_PATH = CACHE_DIR / "last_good_raw.jpg"
FRAME_PATH = CACHE_DIR / "latest.png"  # PNG: JPEG would smear pixel-art edges
STATE_PATH = CACHE_DIR / "state.json"
TFL_LIST_URL = "https://api.tfl.gov.uk/Place/Type/JamCam"
USER_AGENT = "cctv-frame/0.2 (private non-commercial display)"
STYLES = ("pixel", "real")

log = logging.getLogger("cctv_frame")


def load_config(path, need_url=True):
    with open(path) as f:
        cfg = json.load(f)
    cfg.setdefault("style", "pixel")
    cfg.setdefault("pixel", {})
    cfg.setdefault("interval_seconds", 60)
    cfg.setdefault("timeout_seconds", 15)
    cfg.setdefault("image_scale", 0.92)   # fraction of screen the image fills
    cfg.setdefault("brightness", 0.85)    # <1 dims the image for the glass look
    cfg.setdefault("screen_width", None)  # None = detect from display
    cfg.setdefault("screen_height", None)
    if cfg["style"] not in STYLES:
        sys.exit(f"config.json: style must be one of {STYLES}")
    if need_url and not cfg.get("image_url"):
        sys.exit("config.json: set image_url (run with --list-tfl to find one)")
    return cfg


def load_saved_style():
    try:
        style = json.loads(STATE_PATH.read_text()).get("style")
    except (OSError, ValueError):
        return None
    return style if style in STYLES else None


def save_style(style):
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps({"style": style}))
    os.replace(tmp, STATE_PATH)


def fetch_image(url, timeout):
    resp = requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    img = Image.open(io.BytesIO(resp.content))
    img.load()  # force decode so truncated JPEGs fail here, not on screen
    return img.convert("RGB")


def _place(fitted, width, height, brightness):
    if brightness != 1.0:
        fitted = ImageEnhance.Brightness(fitted).enhance(brightness)
    canvas = Image.new("RGB", (width, height), (0, 0, 0))
    canvas.paste(fitted, ((width - fitted.width) // 2, (height - fitted.height) // 2))
    return canvas


def render(img, cfg, style, width, height):
    """Render a camera image to a full-screen frame, letterboxed on pure black."""
    scale = cfg["image_scale"]
    if style == "pixel":
        # Integer factor only: fractional nearest-neighbor makes uneven pixels.
        # Pick the factor nearest the requested art width, then size the art so
        # factor * art fills the same box the real image would.
        fit_w = min(width * scale, height * scale * img.width / img.height)
        factor = max(1, round(fit_w / cfg["pixel"].get("width", 128)))
        art = pixelate(img, {**cfg["pixel"], "width": int(fit_w // factor)})
        fitted = art.resize((art.width * factor, art.height * factor), Image.NEAREST)
    else:
        box = (max(1, int(width * scale)), max(1, int(height * scale)))
        fitted = ImageOps.contain(img, box, Image.LANCZOS)
    return _place(fitted, width, height, cfg["brightness"])


def atomic_save(img, path):
    tmp = path.with_name(path.stem + ".tmp" + path.suffix)
    img.save(tmp)
    os.replace(tmp, path)


def load_last_good():
    try:
        img = Image.open(RAW_PATH)
        img.load()
        return img.convert("RGB")
    except (OSError, ValueError):
        return None


class Fetcher(threading.Thread):
    """Background loop: pull the camera, keep the newest good image in memory."""

    def __init__(self, cfg):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.lock = threading.Lock()
        self.image = load_last_good()
        self.version = 0 if self.image is None else 1
        self.stop_event = threading.Event()

    def fetch_once(self):
        try:
            img = fetch_image(self.cfg["image_url"], self.cfg["timeout_seconds"])
        except (requests.RequestException, OSError) as exc:
            log.warning("fetch failed, keeping last good image: %s", exc)
            return False
        atomic_save(img, RAW_PATH)
        with self.lock:
            self.image = img
            self.version += 1
        log.info("fetched %dx%d", img.width, img.height)
        return True

    def run(self):
        while not self.stop_event.is_set():
            self.fetch_once()
            self.stop_event.wait(self.cfg["interval_seconds"])

    def snapshot(self):
        with self.lock:
            return self.version, self.image


def run_display(cfg, style):
    import tkinter as tk
    from PIL import ImageTk

    root = tk.Tk()
    root.title("cctv-frame")
    root.configure(bg="black", cursor="none")
    root.attributes("-fullscreen", True)
    root.bind("<Escape>", lambda _e: root.destroy())

    width = cfg["screen_width"] or root.winfo_screenwidth()
    height = cfg["screen_height"] or root.winfo_screenheight()
    label = tk.Label(root, bg="black", bd=0, highlightthickness=0)
    label.pack(fill="both", expand=True)

    fetcher = Fetcher(cfg)
    fetcher.start()
    state = {"shown": None, "photo": None, "style": style}

    def toggle(_event=None):
        state["style"] = STYLES[(STYLES.index(state["style"]) + 1) % len(STYLES)]
        save_style(state["style"])
        log.info("style -> %s", state["style"])
        refresh(reschedule=False)

    def refresh(reschedule=True):
        version, img = fetcher.snapshot()
        key = (version, state["style"])
        if img is not None and key != state["shown"]:
            frame = render(img, cfg, state["style"], width, height)
            atomic_save(frame, FRAME_PATH)
            state["photo"] = ImageTk.PhotoImage(frame)  # keep a ref or Tk drops it
            label.configure(image=state["photo"])
            state["shown"] = key
        if reschedule:
            root.after(1000, refresh)

    for key in ("<space>", "p", "P"):
        root.bind(key, toggle)
    refresh()
    root.mainloop()
    fetcher.stop_event.set()


def run_once(cfg, style):
    fetcher = Fetcher(cfg)
    ok = fetcher.fetch_once()
    _, img = fetcher.snapshot()
    if img is None:
        sys.exit("no image fetched and no cached image to fall back on")
    width = cfg["screen_width"] or 1024
    height = cfg["screen_height"] or 600
    atomic_save(render(img, cfg, style, width, height), FRAME_PATH)
    print(f"{'fetched' if ok else 'used cached image'} ({style}) -> {FRAME_PATH}")


def run_preview(cfg, path):
    img = Image.open(path).convert("RGB")
    width = cfg["screen_width"] or 1024
    height = cfg["screen_height"] or 600
    frames = [render(img, cfg, s, width, height) for s in ("real", "pixel")]
    sheet = Image.new("RGB", (width * 2, height))
    for i, f in enumerate(frames):
        sheet.paste(f, (i * width, 0))
    out = CACHE_DIR / "preview.png"
    sheet.save(out)
    print(f"real | pixel -> {out}")


def list_tfl(name_filter):
    resp = requests.get(TFL_LIST_URL, timeout=30, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    needle = (name_filter or "").lower()
    for place in resp.json():
        props = {p["key"]: p["value"] for p in place.get("additionalProperties", [])}
        if needle in place.get("commonName", "").lower() and props.get("available") == "true":
            print(f"{place['commonName']}\n    {props.get('imageUrl')}")


NON_SNAPSHOT_HINTS = ("youtube.com", "youtu.be", "earthcam.com", "skylinewebcams.com",
                      ".m3u8", ".mp4", ".html", "/embed")
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")


def _km(lat1, lng1, lat2, lng2):
    from math import asin, cos, radians, sin, sqrt
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


def list_osiris(base_url, region=None, near=None, radius_km=25, limit=30, probe=False):
    """Use a local Osiris instance as a camera catalogue; print still-image feeds.

    The frame fetches the chosen feed_url directly from the agency, not through
    Osiris, so it keeps working when Osiris is off and sends an honest User-Agent.
    """
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
    for dist, kind, cam in cams[:limit]:
        if probe:
            try:
                r = requests.get(cam["feed_url"], timeout=10, headers={"User-Agent": USER_AGENT})
                kind = "OK" if r.ok and r.headers.get("content-type", "").startswith("image/") \
                    else f"FAIL {r.status_code} {r.headers.get('content-type', '')}"
            except requests.RequestException as exc:
                kind = f"FAIL {type(exc).__name__}"
        where = f"{dist:5.1f} km" if dist is not None else cam.get("country", "")
        print(f"[{kind}] {cam.get('name')} · {cam.get('city', '')} · {cam.get('source')} · {where}\n"
              f"    {cam['feed_url']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--config", default=str(HERE / "config.json"))
    parser.add_argument("--style", choices=STYLES, help="override config/saved style")
    parser.add_argument("--once", action="store_true", help="render one frame, no GUI")
    parser.add_argument("--preview", metavar="IMAGE",
                        help="render a local image in both styles, no network")
    parser.add_argument("--list-tfl", nargs="?", const="", metavar="FILTER",
                        help="list available TfL JamCams (optionally filtered by name)")
    parser.add_argument("--list-osiris", action="store_true",
                        help="list still-image cameras from a running Osiris instance")
    parser.add_argument("--osiris", default="http://localhost:3000", metavar="URL",
                        help="Osiris base URL (default: %(default)s)")
    parser.add_argument("--region", help="Osiris region, e.g. uk, texas, asia, hongkong")
    parser.add_argument("--near", metavar="LAT,LNG", help="only cameras near this point")
    parser.add_argument("--radius", type=float, default=25, help="km, with --near")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--probe", action="store_true",
                        help="with --list-osiris: fetch each listed feed to confirm it serves an image")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.list_tfl is not None:
        list_tfl(args.list_tfl)
        return
    if args.list_osiris:
        near = tuple(float(v) for v in args.near.split(",")) if args.near else None
        list_osiris(args.osiris, args.region, near, args.radius, args.limit, args.probe)
        return
    CACHE_DIR.mkdir(exist_ok=True)
    cfg = load_config(args.config, need_url=not args.preview)
    if args.preview:
        run_preview(cfg, args.preview)
        return
    # Precedence: CLI flag > last toggle on this device > config default.
    style = args.style or load_saved_style() or cfg["style"]
    if args.once:
        run_once(cfg, style)
    else:
        run_display(cfg, style)


if __name__ == "__main__":
    main()
