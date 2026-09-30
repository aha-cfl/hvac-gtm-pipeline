#!/usr/bin/env python3
"""
Prototype 1 — "black glass" CCTV frame.

Fetches one public traffic-camera JPEG on a timer and shows it fullscreen,
centered on pure black. Keeps a last-good copy on disk so a dead feed or a
power cut never leaves the screen blank.

Usage:
    python frame.py                 # fullscreen display (Esc to quit)
    python frame.py --once          # fetch + render one frame to cache/, no GUI
    python frame.py --list-tfl ABC  # list TfL JamCams whose name contains "ABC"
"""

import argparse
import io
import json
import logging
import os
import sys
import threading
import time
from pathlib import Path

import requests
from PIL import Image, ImageEnhance, ImageOps

HERE = Path(__file__).resolve().parent
CACHE_DIR = HERE / "cache"
RAW_PATH = CACHE_DIR / "last_good_raw.jpg"
FRAME_PATH = CACHE_DIR / "latest.jpg"
TFL_LIST_URL = "https://api.tfl.gov.uk/Place/Type/JamCam"
USER_AGENT = "cctv-frame/0.1 (private non-commercial display)"

log = logging.getLogger("cctv_frame")


def load_config(path):
    with open(path) as f:
        cfg = json.load(f)
    cfg.setdefault("interval_seconds", 60)
    cfg.setdefault("timeout_seconds", 15)
    cfg.setdefault("image_scale", 0.92)   # fraction of screen the image fills
    cfg.setdefault("brightness", 0.85)    # <1 dims the image for the glass look
    cfg.setdefault("screen_width", None)  # None = detect from display
    cfg.setdefault("screen_height", None)
    if not cfg.get("image_url"):
        sys.exit("config.json: set image_url (run with --list-tfl to find one)")
    return cfg


def fetch_image(url, timeout):
    resp = requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    img = Image.open(io.BytesIO(resp.content))
    img.load()  # force decode so truncated JPEGs fail here, not on screen
    return img.convert("RGB")


def compose(img, width, height, scale, brightness):
    """Fit the camera image inside the screen, letterboxed on pure black."""
    canvas = Image.new("RGB", (width, height), (0, 0, 0))
    box = (max(1, int(width * scale)), max(1, int(height * scale)))
    fitted = ImageOps.contain(img, box, Image.LANCZOS)
    if brightness != 1.0:
        fitted = ImageEnhance.Brightness(fitted).enhance(brightness)
    canvas.paste(fitted, ((width - fitted.width) // 2, (height - fitted.height) // 2))
    return canvas


def atomic_save(img, path):
    tmp = path.with_suffix(".tmp")
    img.save(tmp, "JPEG", quality=92)
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


def run_display(cfg):
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
    state = {"shown": -1, "photo": None}

    def refresh():
        version, img = fetcher.snapshot()
        if img is not None and version != state["shown"]:
            frame = compose(img, width, height, cfg["image_scale"], cfg["brightness"])
            atomic_save(frame, FRAME_PATH)
            state["photo"] = ImageTk.PhotoImage(frame)  # keep a ref or Tk drops it
            label.configure(image=state["photo"])
            state["shown"] = version
        root.after(1000, refresh)

    refresh()
    root.mainloop()
    fetcher.stop_event.set()


def run_once(cfg):
    fetcher = Fetcher(cfg)
    ok = fetcher.fetch_once()
    _, img = fetcher.snapshot()
    if img is None:
        sys.exit("no image fetched and no cached image to fall back on")
    width = cfg["screen_width"] or 1024
    height = cfg["screen_height"] or 600
    atomic_save(compose(img, width, height, cfg["image_scale"], cfg["brightness"]), FRAME_PATH)
    print(f"{'fetched' if ok else 'used cached image'} -> {FRAME_PATH}")


def list_tfl(name_filter):
    resp = requests.get(TFL_LIST_URL, timeout=30, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    needle = (name_filter or "").lower()
    for place in resp.json():
        props = {p["key"]: p["value"] for p in place.get("additionalProperties", [])}
        if needle in place.get("commonName", "").lower() and props.get("available") == "true":
            print(f"{place['commonName']}\n    {props.get('imageUrl')}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--config", default=str(HERE / "config.json"))
    parser.add_argument("--once", action="store_true", help="render one frame, no GUI")
    parser.add_argument("--list-tfl", nargs="?", const="", metavar="FILTER",
                        help="list available TfL JamCams (optionally filtered by name)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.list_tfl is not None:
        list_tfl(args.list_tfl)
        return
    CACHE_DIR.mkdir(exist_ok=True)
    cfg = load_config(args.config)
    if args.once:
        run_once(cfg)
    else:
        run_display(cfg)


if __name__ == "__main__":
    main()
