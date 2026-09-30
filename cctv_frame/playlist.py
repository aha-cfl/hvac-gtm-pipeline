"""World playlist: which camera to show now.

Modes:
    auto    rotate through cameras currently in daylight (falls back to all
            cameras when the whole playlist is dark)
    all     rotate through every camera, day or night
    pinned  hold one camera
"""

import json
import os
import re

from sun import phase

MODES = ("auto", "all", "pinned")


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48] or "cam"


def load_playlist(path, cfg):
    """Cameras from playlist.json, else the single image_url in config.json."""
    try:
        with open(path) as f:
            cams = json.load(f)["cameras"]
    except FileNotFoundError:
        cams = [{"name": cfg.get("camera_name", "Camera"), "image_url": cfg["image_url"]}]
    out = []
    for cam in cams:
        if cam.get("enabled", True) is False or not cam.get("image_url"):
            continue
        cam = dict(cam)
        cam.setdefault("name", "Camera")
        cam.setdefault("id", slug(cam["name"]))
        out.append(cam)
    if not out:
        raise SystemExit(f"{path}: no enabled cameras")
    return out


def add_to_playlist(path, cams):
    """Append cameras (skipping duplicate URLs) and return how many were added."""
    try:
        with open(path) as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {"cameras": []}
    have = {c.get("image_url") for c in data["cameras"]}
    added = [c for c in cams if c["image_url"] not in have]
    data["cameras"].extend(added)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)
    return len(added)


def cam_phase(cam, when):
    if cam.get("lat") is None or cam.get("lng") is None:
        return "day"  # unknown location: assume viewable
    return phase(cam["lat"], cam["lng"], when)


class Rotator:
    def __init__(self, cams, rotate_seconds=120, mode="auto", pinned_id=None):
        self.cams = cams
        self.rotate_seconds = rotate_seconds
        self.mode = mode if mode in MODES else "auto"
        self.index = 0
        if pinned_id:
            self.index = next((i for i, c in enumerate(cams) if c["id"] == pinned_id), 0)
        self.next_at = None
        self.offline = set()  # camera ids with no image and failing fetches

    @property
    def current(self):
        return self.cams[self.index]

    def eligible(self, when):
        live = [i for i, c in enumerate(self.cams) if c["id"] not in self.offline]
        if not live:
            live = list(range(len(self.cams)))
        if self.mode == "auto":
            lit = [i for i in live if cam_phase(self.cams[i], when) != "night"]
            return lit or live
        return live

    def step(self, when, direction=1):
        """Move to the next eligible camera in playlist order."""
        pool = self.eligible(when)
        n = len(self.cams)
        for k in range(1, n + 1):
            i = (self.index + direction * k) % n
            if i in pool:
                self.index = i
                return
        self.index = pool[0]

    def start(self, now, when):
        if self.mode == "auto" and self.index not in self.eligible(when):
            self.step(when)
        self.next_at = now + self.rotate_seconds

    def tick(self, now, when):
        """Advance when the timer runs out or the current camera is dead.
        Returns True if the camera changed."""
        if self.mode == "pinned":
            return False
        if now >= self.next_at or self.current["id"] in self.offline:
            before = self.index
            self.step(when)
            self.next_at = now + self.rotate_seconds
            return self.index != before
        return False

    def jump(self, index, now):
        self.index = index % len(self.cams)
        self.next_at = now + self.rotate_seconds

    def set_mode(self, mode, now, when):
        self.mode = mode
        if mode != "pinned":
            self.start(now, when)

    def seconds_left(self, now):
        return None if self.mode == "pinned" else max(0, int(self.next_at - now))
