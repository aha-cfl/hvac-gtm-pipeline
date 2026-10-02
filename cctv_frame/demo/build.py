#!/usr/bin/env python3
"""
Build the five self-contained prototype pages (P1-P5) from engine.html.

Each page embeds its camera captures as data URIs, so it runs anywhere
(including as a published artifact) without a server. The motion is
simulated from real CCTV captures; the live streams play in web.py.

    python demo/build.py ASSETS_DIR OUT_DIR

ASSETS_DIR must hold the capture images named in VIEWS and world.txt
(a 90x180 grid of 0/1 land cells, north to south, 2 degrees each).
"""

import base64
import io
import json
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from pixelate import PALETTES  # noqa: E402

CITIES = [
    {"id": "seoul", "city": "Seoul", "country": "KR", "lat": 37.5721, "lng": 127.0235, "tz": "Asia/Seoul",
     "views": [("Cheonggyecheon 8-ga", "osiris_seoul.png"), ("City Hall, Sejongdae-ro", "seoul_cityhall.png"),
               ("Jangchung-dong", "seoul_jangchung.png"), ("Namsan Tunnel 2", "seoul_namsan.png")]},
    {"id": "taipei", "city": "Taipei", "country": "TW", "lat": 25.0504, "lng": 121.5109, "tz": "Asia/Taipei",
     "views": [("Longmen Building rooftop", "osiris_taiwan.png"), ("Fuxing North Road", "taipei_fuxing.png"),
               ("Heping West Road", "taipei_heping.png"), ("Zhonghua & Aiguo Road", "taipei_zhonghua.png")]},
    {"id": "southampton", "city": "Southampton", "country": "US", "lat": 40.884, "lng": -72.3897,
     "tz": "America/New_York", "views": [("Harbor", "hamptons_harbor.png")]},
]

HONEST = ("Simulated stream: real CCTV captures (Seoul TOPIS and Twipcam via Osiris, Hamptons Cams) with "
          "slow camera drift, sensor grain and a ticking timestamp. Published pages can't load outside "
          "video, so the live streams play in the local version (<b>web.py</b>). Private prototype only.")

PAGES = [
    dict(level=1, slug="p1-window", title="Visual Radio Window", tag="PROTOTYPE 1",
         heading="Window: one city, one angle",
         lede="A live view of Seoul behind black glass. No controls: it powers on with a CRT flicker and static, "
              "shows the station ID, and holds the signal through weak moments.",
         cities=["seoul"], angles=False,
         note="<b>Tests:</b> do people keep looking at a live view of somewhere else? "
              "<span class='keys'>Tap the screen to replay the tune-in.</span><br>" + HONEST),
    dict(level=2, slug="p2-styles", title="Visual Radio Styles", tag="PROTOTYPE 2",
         heading="Styled window: real, pixel, vintage",
         lede="The same single view, plus three style buttons. Pixel art switches to its night palette when it's "
              "dark in Seoul; vintage adds film tone, grain, scanlines and a vignette.",
         cities=["seoul"], angles=False,
         note="<b>Tests:</b> does a style turn a camera into art people would hang? "
              "<span class='keys'>Keys: P cycles styles · tap the screen to re-tune.</span><br>" + HONEST),
    dict(level=3, slug="p3-tuner", title="Visual Radio Tuner", tag="PROTOTYPE 3",
         heading="Visual radio: knob, stations, shuffle",
         lede="Three cities on the dial. Turn the knob (drag, scroll, or arrow keys) to tune with static between "
              "stations. SCAN drifts between places in daylight, SHUFFLE jumps at random, HOLD keeps a station.",
         cities=["southampton", "taipei", "seoul"], angles=False,
         note="<b>Tests:</b> do people tune in and come back to favourite stations? "
              "<span class='keys'>Keys: ←/→ tune · P style · S shuffle · H hold. Turn on STATIC FX for sound.</span><br>" + HONEST),
    dict(level=4, slug="p4-world-dial", title="Visual Radio World Dial", tag="PROTOTYPE 4",
         heading="World dial: minimap, angles, shuffle",
         lede="A pixel world map with live day and night shading. The knob moves a needle west to east across "
              "the stations; click a lit city to jump there. ANGLE switches between several cameras in the same city.",
         cities=["southampton", "taipei", "seoul"], angles=True,
         note="<b>Tests:</b> does choosing the place, and the angle, beat a curated scan? "
              "<span class='keys'>Keys: ←/→ tune · ↑ angle · P style · S shuffle · H hold.</span><br>" + HONEST),
    dict(level=5, slug="p5-frame", title="Visual Radio Frame", tag="PROTOTYPE 5",
         heading="The frame: everything in one object",
         lede="The physical version as one device: power button with CRT on/off, tuning knob on the side, style, "
              "mode and angle buttons. Turning the knob brings up the world dial on the glass for a few seconds.",
         cities=["southampton", "taipei", "seoul"], angles=True,
         note="<b>Tests:</b> is a physical instrument worth a hardware price? On the real frame the knob is a "
              "rotary encoder and the buttons are GPIO switches sending these same actions. "
              "<span class='keys'>Keys: ←/→ tune · ↑ angle · P style · S shuffle · H hold · M map.</span><br>" + HONEST),
]


def data_uri(path, max_w=960):
    im = Image.open(path).convert("RGB")
    if im.width > max_w:
        im = im.resize((max_w, round(max_w * im.height / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=86)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def build(assets, out):
    out.mkdir(parents=True, exist_ok=True)
    engine = (HERE / "engine.html").read_text()
    world = (assets / "world.txt").read_text().split()
    uris = {}
    for page in PAGES:
        stations = []
        for cid in page["cities"]:
            c = next(x for x in CITIES if x["id"] == cid)
            views = c["views"] if page["angles"] else c["views"][:1]
            for _, f in views:
                uris.setdefault(f, data_uri(assets / f))
            stations.append({k: c[k] for k in ("id", "city", "country", "lat", "lng", "tz")}
                            | {"views": [{"name": n, "img": uris[f]} for n, f in views]})
        data = {"level": page["level"], "stations": stations, "world": world,
                "palettes": {"city16": PALETTES["city16"], "night16": PALETTES["night16"]},
                "scanMs": 40000, "shuffleMs": 20000, "note": page["note"]}
        html = (engine.replace("__TITLE__", page["title"]).replace("__TAG__", page["tag"])
                .replace("__HEADING__", page["heading"]).replace("__LEDE__", page["lede"])
                .replace("__DATA__", json.dumps(data, separators=(",", ":"))))
        path = out / f"{page['slug']}.html"
        path.write_text(html)
        print(f"{path}  {len(html) // 1024} KB")


if __name__ == "__main__":
    build(Path(sys.argv[1]), Path(sys.argv[2]))
