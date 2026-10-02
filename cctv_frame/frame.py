#!/usr/bin/env python3
"""
Visual radio — tune into the sights of local life in other places.

Each station is a public camera. SCAN drifts between stations that are in
daylight; TUNED holds one. Changing station plays a burst of static and a
station ID (city, local time, day/night), like a radio dial.

Two picture styles:
    real   the camera image as-is, dimmed behind black glass
    pixel  Aseprite-style sprite art; day and night palettes follow the sun

Usage:
    python frame.py                     # fullscreen (keys below), Esc quits
    python frame.py --once              # render one frame to cache/latest.png, no GUI
    python frame.py --once --sidebar --at 2026-09-30T12:00Z   # UI snapshot at a given time
    python frame.py --preview photo.jpg # real vs pixel side by side -> cache/preview.png
    python frame.py --list-osiris --near 22.28,114.16 --save  # add [OK] cams as stations
    python frame.py --list-tfl ABC      # list TfL JamCams whose name contains "ABC"

Keys: S/Tab stations sidebar · ←/→ tune · ↑/↓ select · Enter tune+hold ·
      A scan mode · P/Space real↔pixel · Esc close sidebar/quit. Taps work too.
"""

import argparse
import io
import json
import logging
import os
import random
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageEnhance, ImageOps

from pixelate import pixelate
from playlist import Rotator, cam_phase, load_playlist
from sidebar import draw_sidebar, font
from sun import local_time

HERE = Path(__file__).resolve().parent
CACHE_DIR = HERE / "cache"
CAM_CACHE = CACHE_DIR / "stations"
FRAME_PATH = CACHE_DIR / "latest.png"  # PNG: JPEG would smear pixel-art edges
STATE_PATH = CACHE_DIR / "state.json"
PLAYLIST_PATH = HERE / "playlist.json"
USER_AGENT = "cctv-frame/0.3 (private non-commercial display)"
STYLES = ("real", "pixel")
OFFLINE_AFTER_FAILS = 2
OFFLINE_RETRY_SECONDS = 600
RETRY_SECONDS = 5

log = logging.getLogger("cctv_frame")


def load_config(path):
    with open(path) as f:
        cfg = json.load(f)
    cfg.setdefault("style", "real")
    cfg.setdefault("pixel", {})
    cfg["pixel"].setdefault("night_palette", "night16")
    cfg.setdefault("interval_seconds", 60)
    cfg.setdefault("rotate_seconds", 120)
    cfg.setdefault("sidebar_timeout_seconds", 20)
    cfg.setdefault("station_id_seconds", 5)
    cfg.setdefault("static_seconds", 0.6)
    cfg.setdefault("timeout_seconds", 15)
    cfg.setdefault("image_scale", 0.92)   # fraction of screen the image fills
    cfg.setdefault("brightness", 0.85)    # <1 dims the image for the glass look
    cfg.setdefault("screen_width", None)  # None = detect from display
    cfg.setdefault("screen_height", None)
    if cfg["style"] not in STYLES:
        sys.exit(f"config.json: style must be one of {STYLES}")
    return cfg


def load_state():
    try:
        return json.loads(STATE_PATH.read_text())
    except (OSError, ValueError):
        return {}


def save_state(state):
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    os.replace(tmp, STATE_PATH)


def fetch_image(url, timeout):
    resp = requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    img = Image.open(io.BytesIO(resp.content))
    img.load()  # force decode so truncated JPEGs fail here, not on screen
    return img.convert("RGB")


def atomic_save(img, path):
    tmp = path.with_name(path.stem + ".tmp" + path.suffix)
    img.save(tmp)
    os.replace(tmp, path)


def _place(fitted, width, height, brightness):
    if brightness != 1.0:
        fitted = ImageEnhance.Brightness(fitted).enhance(brightness)
    canvas = Image.new("RGB", (width, height), (0, 0, 0))
    canvas.paste(fitted, ((width - fitted.width) // 2, (height - fitted.height) // 2))
    return canvas


def render(img, cfg, style, width, height, palette=None):
    """Render a camera image to a full-screen frame, letterboxed on pure black."""
    scale = cfg["image_scale"]
    if style == "pixel":
        settings = {k: v for k, v in cfg["pixel"].items() if k != "night_palette"}
        if palette:
            settings["palette"] = palette
        # Integer factor only: fractional nearest-neighbor makes uneven pixels.
        # Pick the factor nearest the requested art width, then size the art so
        # factor * art fills the same box the real image would.
        fit_w = min(width * scale, height * scale * img.width / img.height)
        factor = max(1, round(fit_w / settings.get("width", 128)))
        art = pixelate(img, {**settings, "width": int(fit_w // factor)})
        fitted = art.resize((art.width * factor, art.height * factor), Image.NEAREST)
    else:
        box = (max(1, int(width * scale)), max(1, int(height * scale)))
        fitted = ImageOps.contain(img, box, Image.LANCZOS)
    return _place(fitted, width, height, cfg["brightness"])


def static_frame(width, height, seed=None):
    """Tuning static: coarse dark noise, like a dial between stations."""
    rnd = random.Random(seed)
    w, h = max(1, width // 8), max(1, height // 8)
    noise = Image.new("L", (w, h))
    noise.putdata([int(rnd.random() ** 2.2 * 150) for _ in range(w * h)])
    return noise.resize((width, height), Image.NEAREST).convert("RGB")


def draw_station_id(frame, cam, when, alpha=1.0):
    """Lower-third station ident: CITY · local time · phase."""
    W, H = frame.size
    u = H / 600
    img = frame.copy()
    d = ImageDraw.Draw(img)
    city = (cam.get("city") or cam.get("country") or cam["name"]).upper()
    t = local_time(cam["lng"], when, cam.get("tz")) if cam.get("lng") is not None else ""
    ph = cam_phase(cam, when)
    line1 = city
    line2 = " · ".join(p for p in (cam["name"] if cam["name"].upper() != city else "", t, ph) if p)
    x, y = int(W * 0.06), int(H * 0.80)
    col = tuple(int(c * alpha) for c in (236, 236, 230))
    sub = tuple(int(c * alpha) for c in (150, 152, 156))
    for dx, dy in ((1, 1), (2, 2)):  # soft drop shadow for legibility over bright scenes
        d.text((x + dx, y + dy), line1, font=font(30 * u), fill=(0, 0, 0))
    d.text((x, y), line1, font=font(30 * u), fill=col)
    d.text((x + 1, y + 38 * u + 1), line2, font=font(15 * u), fill=(0, 0, 0))
    d.text((x, y + 38 * u), line2, font=font(15 * u), fill=sub)
    return img


class Fetcher(threading.Thread):
    """Background loop: pull the current station; per-station last-good cache."""

    def __init__(self, cfg):
        super().__init__(daemon=True)
        self.interval = cfg["interval_seconds"]
        self.timeout = cfg["timeout_seconds"]
        self.lock = threading.Lock()
        self.cam = None
        self.image = None
        self.version = 0
        self.fails = {}  # id -> (consecutive failures, last failure time)
        self.wake = threading.Event()
        self.stop_event = threading.Event()

    @staticmethod
    def cache_path(cam):
        return CAM_CACHE / f"{cam['id']}.jpg"

    def set_camera(self, cam):
        with self.lock:
            if self.cam is not None and self.cam["id"] == cam["id"]:
                return
            self.cam = cam
            try:
                img = Image.open(self.cache_path(cam))
                img.load()
                self.image = img.convert("RGB")
            except (OSError, ValueError):
                self.image = None
            self.version += 1
        self.wake.set()

    def fetch_once(self):
        cam = self.cam
        if cam is None:
            return False
        try:
            if not cam.get("image_url"):
                raise OSError("live-stream station: no snapshot (use web.py for video)")
            img = fetch_image(cam["image_url"], self.timeout)
        except (requests.RequestException, OSError) as exc:
            with self.lock:
                n, _ = self.fails.get(cam["id"], (0, 0))
                self.fails[cam["id"]] = (n + 1, time.time())
            log.warning("%s: fetch failed (%s)", cam["name"], exc)
            return False
        atomic_save(img, self.cache_path(cam))
        with self.lock:
            self.fails.pop(cam["id"], None)
            if self.cam is cam:
                self.image = img
                self.version += 1
        log.info("%s: fetched %dx%d", cam["name"], img.width, img.height)
        return True

    def run(self):
        while not self.stop_event.is_set():
            ok = self.fetch_once()
            self.wake.wait(self.interval if ok else min(self.interval, RETRY_SECONDS))
            self.wake.clear()

    def snapshot(self):
        with self.lock:
            return self.version, self.image, (self.cam or {}).get("id")

    def offline_ids(self, now):
        """Stations to skip: repeated failures, or one failure with nothing cached
        to show. Each gets another chance after OFFLINE_RETRY_SECONDS."""
        with self.lock:
            return {cid for cid, (n, at) in self.fails.items()
                    if now - at < OFFLINE_RETRY_SECONDS
                    and (n >= OFFLINE_AFTER_FAILS or not (CAM_CACHE / f"{cid}.jpg").exists())}


class Controller:
    """All display logic, no GUI dependency: tick() returns a new frame or None."""

    def __init__(self, cfg, cams, width, height, style, fetcher, state=None, time_offset=0.0):
        state = state or {}
        self.cfg, self.W, self.H, self.fetcher = cfg, width, height, fetcher
        # Prototype tier (see PROTOTYPES.md): 1 = one camera, real only;
        # 2 = one camera + style toggle; 3 = full visual radio.
        self.level = int(cfg.get("prototype", 3))
        if self.level < 3:
            cams, state = cams[:1], {**state, "mode": "pinned", "pinned": None}
        self.style = "real" if self.level == 1 else style
        self.rot = Rotator(cams, cfg["rotate_seconds"], state.get("mode", "auto"),
                           state.get("pinned"))
        self.selected = self.rot.index
        self.time_offset = time_offset
        self.sidebar = False
        self.sidebar_until = 0.0
        self.static_until = 0.0
        self.ident_until = 0.0
        self.boxes = []
        self._base_key = self._base = self._key = None

    def when(self, now):
        return datetime.fromtimestamp(now + self.time_offset, timezone.utc)

    def start(self, now):
        self.rot.start(now, self.when(now))
        self._tuned(now)

    def _tuned(self, now, static=True):
        self.fetcher.set_camera(self.rot.current)
        self.selected = self.rot.index
        if self.level < 3:  # a window, not a radio: no static, no station ID
            return
        if static:
            self.static_until = now + self.cfg["static_seconds"]
        self.ident_until = now + self.cfg["static_seconds"] + self.cfg["station_id_seconds"]
        self._save()

    def _save(self):
        try:
            save_state({"style": self.style, "mode": self.rot.mode,
                        "pinned": self.rot.current["id"] if self.rot.mode == "pinned" else None})
        except OSError:
            pass

    def _touch(self, now):
        self.sidebar_until = now + self.cfg["sidebar_timeout_seconds"]

    @property
    def animating(self):
        return time.time() < self.static_until

    # --- input -------------------------------------------------------------
    def key(self, k, now):
        k = k.lower()
        allowed = {1: ("escape",), 2: ("escape", "p", "space")}.get(self.level)
        if allowed and k not in allowed:
            return None
        when = self.when(now)
        n = len(self.rot.cams)
        if k in ("s", "tab"):
            self.sidebar = not self.sidebar
        elif k in ("up", "down"):
            self.sidebar = True
            self.selected = (self.selected + (1 if k == "down" else -1)) % n
        elif k in ("return", "kp_enter"):
            self.pin(self.selected, now)
        elif k in ("left", "right"):
            self.rot.jump(self.rot.index + (1 if k == "right" else -1), now)
            self._tuned(now)
        elif k == "a":
            nxt = {"auto": "all", "all": "auto", "pinned": "auto"}[self.rot.mode]
            self.rot.set_mode(nxt, now, when)
            self._tuned(now, static=False)
        elif k in ("p", "space"):
            self.set_style("pixel" if self.style == "real" else "real")
        elif k == "escape":
            if not self.sidebar:
                return "quit"
            self.sidebar = False
        self._touch(now)
        return None

    def pin(self, index, now):
        if self.rot.mode == "pinned" and index == self.rot.index:
            self.rot.set_mode("auto", now, self.when(now))  # tapping the held station releases it
        else:
            self.rot.jump(index, now)
            self.rot.mode = "pinned"
        self._tuned(now)

    def set_style(self, style):
        self.style = style
        if self.level < 3:
            try:  # keep the style choice, leave the radio's mode/station alone
                save_state({**load_state(), "style": style})
            except OSError:
                pass
            return
        self._save()

    def click(self, x, y, now):
        if self.level == 2:
            self.set_style("pixel" if self.style == "real" else "real")
        if self.level < 3:
            return
        self._touch(now)
        if not self.sidebar:
            self.sidebar = True
            return
        for x0, y0, x1, y1, (kind, value) in self.boxes:
            if x0 <= x <= x1 and y0 <= y <= y1:
                if kind == "pin":
                    self.selected = value
                    self.pin(value, now)
                elif kind == "style":
                    self.set_style(value)
                elif kind == "mode":
                    if value == "pinned":
                        if self.rot.mode != "pinned":
                            self.pin(self.rot.index, now)
                    else:
                        self.rot.set_mode(value, now, self.when(now))
                        self._tuned(now, static=False)
                return
        if self.boxes and x < min(b[0] for b in self.boxes):
            self.sidebar = False

    # --- output ------------------------------------------------------------
    def tick(self, now):
        when = self.when(now)
        self.rot.offline = self.fetcher.offline_ids(now)
        if self.rot.tick(now, when):
            self._tuned(now)
        if self.sidebar and now > self.sidebar_until:
            self.sidebar = False

        if now < self.static_until:
            self._key = None
            return static_frame(self.W, self.H)

        version, img, cam_id = self.fetcher.snapshot()
        cam = self.rot.current
        ph = cam_phase(cam, when)
        palette = self.cfg["pixel"]["night_palette"] if ph == "night" else None
        base_key = (version, cam_id, self.style, palette)
        if base_key != self._base_key:
            if img is None:
                base = Image.new("RGB", (self.W, self.H), (0, 0, 0))
                ImageDraw.Draw(base).text((self.W * 0.06, self.H * 0.5), "tuning…",
                                          font=font(self.H / 40), fill=(80, 82, 88))
                self._base = base
            else:
                self._base = render(img, self.cfg, self.style, self.W, self.H, palette)
            self._base_key = base_key

        ident = now < self.ident_until
        fade = min(1.0, (self.ident_until - now) / 1.0) if ident else 0
        key = (base_key, self.sidebar, ident and round(fade, 1),
               (self.selected, self.rot.mode, self.rot.index, self.rot.seconds_left(now),
                when.strftime("%H:%M"), frozenset(self.rot.offline)) if self.sidebar else None)
        if key == self._key:
            return None
        self._key = key
        frame = self._base
        if ident:
            frame = draw_station_id(frame, cam, when, fade)
        if self.sidebar:
            frame, self.boxes = draw_sidebar(frame, self.rot, self.style, self.selected,
                                             when, now, self.rot.offline)
        else:
            self.boxes = []
        return frame


def run_display(cfg, cams, style, state):
    import tkinter as tk
    from PIL import ImageTk

    root = tk.Tk()
    root.title("visual-radio")
    root.configure(bg="black", cursor="none")
    root.attributes("-fullscreen", True)
    width = cfg["screen_width"] or root.winfo_screenwidth()
    height = cfg["screen_height"] or root.winfo_screenheight()
    label = tk.Label(root, bg="black", bd=0, highlightthickness=0)
    label.pack(fill="both", expand=True)

    fetcher = Fetcher(cfg)
    fetcher.start()
    ctl = Controller(cfg, cams, width, height, style, fetcher, state)
    ctl.start(time.time())
    holder = {}

    def loop():
        frame = ctl.tick(time.time())
        if frame is not None:
            holder["photo"] = ImageTk.PhotoImage(frame)  # keep a ref or Tk drops it
            label.configure(image=holder["photo"])
        root.after(80 if ctl.animating else 250, loop)

    def on_key(event):
        if ctl.key(event.keysym, time.time()) == "quit":
            root.destroy()
        return "break"  # stop Tab from moving focus

    root.bind("<Key>", on_key)
    root.bind("<Button-1>", lambda e: ctl.click(e.x, e.y, time.time()))
    loop()
    root.mainloop()
    fetcher.stop_event.set()


def run_once(cfg, cams, style, state, sidebar=False, at=None, out=FRAME_PATH):
    """Headless: fetch the current station once and render one frame."""
    fetcher = Fetcher(cfg)
    width = cfg["screen_width"] or 1024
    height = cfg["screen_height"] or 600
    offset = (at - datetime.now(timezone.utc)).total_seconds() if at else 0.0
    ctl = Controller(cfg, cams, width, height, style, fetcher, state, offset)
    now = time.time()
    ctl.start(now)
    ok = False
    for _ in cams:  # follow the same skip-dead-stations chain the live display does
        ok = fetcher.fetch_once()
        ctl.tick(now)
        if ok or fetcher.snapshot()[1] is not None:
            break
    ctl.static_until = 0  # skip the static burst; keep the station ID
    ctl.sidebar = sidebar
    ctl._touch(now)
    ctl._key = None
    frame = ctl.tick(now)
    atomic_save(frame, out)
    cam = ctl.rot.current
    print(f"{cam['name']} [{cam_phase(cam, ctl.when(now))}] "
          f"{'fetched' if ok else 'cached/none'} ({style}) -> {out}")


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


def main():
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--config", default=str(HERE / "config.json"))
    parser.add_argument("--playlist", default=str(PLAYLIST_PATH))
    parser.add_argument("--style", choices=STYLES, help="override config/saved style")
    parser.add_argument("--prototype", type=int, choices=(1, 2, 3),
                        help="run as prototype tier 1-3 (see PROTOTYPES.md); default: config")
    parser.add_argument("--once", action="store_true", help="render one frame, no GUI")
    parser.add_argument("--sidebar", action="store_true", help="with --once: show the sidebar")
    parser.add_argument("--at", help="with --once: pretend it is this UTC time (ISO 8601)")
    parser.add_argument("--out", help="with --once: output path")
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
    parser.add_argument("--save", action="store_true",
                        help="with --list-osiris: probe and add [OK] cameras to the playlist")
    parser.add_argument("--live", action="store_true",
                        help="with --list-osiris: list live-video cameras (HLS, YouTube) instead of snapshots")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.list_tfl is not None or args.list_osiris:
        from discover import list_osiris, list_tfl
        if args.list_tfl is not None:
            list_tfl(args.list_tfl)
        else:
            near = tuple(float(v) for v in args.near.split(",")) if args.near else None
            list_osiris(args.osiris, args.region, near, args.radius, args.limit, args.probe,
                        args.playlist if args.save else None, args.live)
        return
    CACHE_DIR.mkdir(exist_ok=True)
    CAM_CACHE.mkdir(exist_ok=True)
    cfg = load_config(args.config)
    if args.prototype:
        cfg["prototype"] = args.prototype
    if args.preview:
        run_preview(cfg, args.preview)
        return
    cams = load_playlist(args.playlist, cfg)
    state = load_state()
    # Precedence: CLI flag > last choice on this device > config default.
    style = args.style or (state.get("style") if state.get("style") in STYLES else None) \
        or cfg["style"]
    if args.once:
        at = datetime.fromisoformat(args.at.replace("Z", "+00:00")) if args.at else None
        if at and at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        run_once(cfg, cams, style, state, args.sidebar, at, Path(args.out) if args.out else FRAME_PATH)
    else:
        run_display(cfg, cams, style, state)


if __name__ == "__main__":
    main()
