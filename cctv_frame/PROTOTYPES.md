# Prototype ladder

Each tier is a standalone product that could ship on its own. Each one adds a
single layer of complexity and tests a single riskiest assumption. Kill or
advance a tier on its own evidence, not on the excitement of the next one.

| # | Prototype | New layer | Riskiest assumption | Status | Run |
|---|---|---|---|---|---|
| 1 | **Window** | One live camera, black glass | People keep looking at a live view of somewhere else | Built | `python frame.py --prototype 1` |
| 2 | **Styled Window** | Picture styles: real / pixel / vintage | A style turns a camera feed into art people will pay for | Real + pixel built; vintage to build | `python frame.py --prototype 2` |
| 3 | **Visual Radio** | Stations, SCAN/TUNED, day/night, station ID | People want to *tune in* to many places, not stare at one | Built | `python frame.py --prototype 3` |
| 4 | **World Dial** | Map to choose where to go, multiple angles per place | Choosing the place beats a curated scan | To build | — |
| 5 | **Visual Radio Frame** | Physical object: tuning knob, side controls, all of 1–4 | A physical instrument is worth a hardware price | To build | — |

Tiers 1–3 run from the same code via `--prototype N` (or `"prototype"` in
`config.json`). A lower tier hides the higher tiers' features instead of
forking the code, so every test runs the same fetch/render path.

---

## 1 — Window
- **Is:** one public camera, fullscreen, dimmed behind black glass, refreshed every 60 s. No controls besides Esc.
- **Hardware:** Pi 4 + 7–10" IPS panel + shadow-box frame (~$140–200).
- **Product shape:** an ambient frame, or a free screensaver/TV app as the cheapest version.
- **Test:** 5–10 people live with it for 2 weeks.
- **Advance if:** at least half still glance at it daily in week 2, and at least one asks to keep it.
- **Kill if:** it becomes wallpaper by day 4.

## 2 — Styled Window
- **Is:** Window, plus a style button.
  - `real`: built.
  - `pixel`: built, `city16` by day and `night16` by night.
  - `vintage`: to build. Film grain, faded warm tone curve, vignette, optional CRT scanlines.
- **Product shape:** art object or gift ($149–199 hypothesis). Pixel mode doubles as the privacy layer.
- **Test:** show the same frame in each style and ask: *which would you hang? what would you pay?*
- **Advance if:** a style raises stated price or gift intent over `real` by a clear margin.
- **Kill if:** everyone picks `real` and the style is a toggle nobody touches.

## 3 — Visual Radio
- **Is:** a playlist of stations around the world.
  - SCAN ☀ drifts between places in daylight; SCAN ALL includes night; TUNED holds one.
  - Static and a station ID play on every change. A station list slides in on tap.
- **Product shape:** software subscription (station packs, $3–5/mo hypothesis) on frames, TVs or laptops.
- **Test:** 10–20 users on their own screens for 2 weeks.
- **Measure:** tunes per day, how often each station is held, which stations get held.
- **Advance if:** users tune several times a week and hold the same 2–3 stations. Having favorites is the signal.
- **Kill if:** everyone leaves it on SCAN forever. That means it's a slideshow, not a radio.

## 4 — World Dial (to build)
- **Is:** choose *where* to go, not just *which* station is next.
  - **Map:** a dark pixel world map with lit dots on stations in daylight. The dial pans along longitudes like an FM band, so turning the dial travels east or west through time zones.
  - **Angles:** a place holds several cameras (e.g. Hong Kong: harbour, market street, highway). Tuning picks the place; a second control flips angles.
  - **Phone companion (optional):** browse the map, favorite places, push them to the frame.
- **Data change:** `playlist.json` stations become places with an `angles` list.
- **Test:** the same users as P3, A/B: map + angles vs. P3 scan only.
- **Advance if:** map users hold more distinct places and stay longer per session.
- **Kill if:** the map is used once as a demo and then never opened.

## 5 — Visual Radio Frame (to build)
- **Is:** the object.
  - **Tuning knob** (rotary encoder with push): turn to tune, with a static burst between stations. Push to hold or release. Long-press opens the World Dial map.
  - **Side controls:** a style selector (real / pixel / vintage) and an angle button.
  - Black glass front with no visible bezel; the station ID card is the only on-screen text.
- **Hardware delta from P1:** KY-040 rotary encoder (~$2–5), 2 tactile buttons, a knob cap, GPIO wiring, a side cut-out in the frame.
- **Code delta:** a GPIO input module that emits the same key events the controller already handles:
  - turn = ←/→
  - push = Enter
  - long-press = map
  - buttons = P / angle
- **Product shape:** device at $299–399 (hypothesis), with the P3/P4 subscription on top.
- **Test:** 5 hand-built units in homes for 2 weeks, plus a fake-door pre-order page with a price.
- **Advance if:** the knob gets used more than touch did in P3, and the pre-order page converts.
- **Kill if:** people tune by phone and ignore the knob. Then the product is P3/P4 software.

---

## Gating issues for every tier (before any sale)
- **Licensing:** commercial use needs open-data licenses that allow it with attribution, such as TfL, data.gov.hk and Digitraffic. Aggregated or commercial webcams (Skyline, EarthCam, Osiris's proxied feeds) are out.
- **Privacy:** prefer wide views. Pixel or vintage styles reduce identifiability; `real` at CCTV resolution mostly does too, but check each station.
- **Station curation:** 8–12 hero stations beat 17,000 random ones at every tier.
