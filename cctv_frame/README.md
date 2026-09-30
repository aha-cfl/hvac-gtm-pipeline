# cctv_frame — visual radio

Tune into the sights of local life in other places. Radio lets you hear what a
city is talking about; this lets you see it.

Each **station** is a public camera. The frame shows one station fullscreen
behind black glass, refreshed every 60 s.
- **SCAN ☀** drifts between stations that are currently in daylight, one every 2 min.
- **SCAN ALL** includes night stations.
- **TUNED** holds one station.

Changing station plays a short burst of static, then a station ID (city, local time, day/night).

| Style | Look | Night |
|---|---|---|
| `real` (default) | The camera image, dimmed behind glass | As the camera sees it |
| `pixel` | Aseprite-style sprite art, crisp square pixels | Switches automatically from `city16` to `night16` once the sun is 4° below the horizon at that camera |

Daylight is computed from each station's lat/lng and the current UTC time (`sun.py`).
No time-zone database or network call is needed.

### Controls (keyboard or touch)

| Key | Tap | Action |
|---|---|---|
| S / Tab | tap anywhere | Open or close the station list (hides after 20 s) |
| ← / → | — | Tune to the previous or next station |
| ↑ / ↓, Enter | tap a station | Select a station and hold it (TUNED). Tap it again to resume scanning |
| A | SCAN chips | Switch between SCAN ☀ and SCAN ALL |
| P / Space | REAL/PIXEL chips | Switch picture style |
| Esc | — | Close the list, then quit |

Style, mode and the held station are saved in `cache/state.json`.
Precedence: `--style` flag, then the last choice on this device, then `config.json`.

### Stations (`playlist.json`)

Each station has `name`, `city`, `lat`, `lng` and `image_url`. `tz` (IANA name, e.g. `Asia/Hong_Kong`) is optional; without it the local time shown is mean solar time (`~`).

The starter list has Hong Kong Transport Department and NZTA open-data cameras, taken from Osiris's own source. They span 12+ time zones, but none have been verified live yet.

- A station that fails once with nothing cached is skipped at once.
- A station that fails twice is skipped even if it has a cached image.
- Either kind gets another chance after 10 minutes.

To add verified stations, see [Find cameras with Osiris](#find-cameras-with-osiris).

Private, non-commercial use only. TfL JamCams come under TfL's open-data terms,
which require the attribution "Powered by TfL Open Data". Check any other source's terms before you add it.

## Parts (Prototype 1)

| Part | Pick | ~Cost |
|---|---|---|
| Computer | Raspberry Pi 4 (2 GB) or Pi 5 + official PSU | $45–80 |
| Storage | 32 GB A1/A2 microSD | $10 |
| Screen | 7" 1024×600 **IPS** HDMI panel (USB-powered) | $45–60 |
| Cables | micro-HDMI→HDMI (short or flat/right-angle), USB-A→USB-C/micro for panel power | $10 |
| Frame | Black shadow box, 8×10", ≥1.5" deep | $15–25 |
| Mat | Black mat, window cut to panel **active area** (not bezel) | $5–15 |
| Glass look (optional) | 2–3 mm dark-tint/smoked acrylic cut to frame size | $10–20 |
| Mounting | VHB foam tape, velcro strips, cable clips | $5 |

Tools: utility knife, metal straightedge, tape measure, precision screwdrivers.

**Zero-hardware test first:** run it on your laptop (steps below). That proves the software before you buy anything.

## Run on a laptop (Windows/macOS/Linux)

```bash
cd cctv_frame
pip install -r requirements.txt
python frame.py --list-tfl "Oxford"   # pick a camera, paste its imageUrl into config.json
python frame.py                       # fullscreen visual radio; keys above, Esc quits
```

`python frame.py --preview any_photo.jpg` writes `cache/preview.png` with the two styles side by side, without any network. Use it to tune the pixel settings.

`python frame.py --once` renders a single frame to `cache/latest.png` without opening a window. Add `--sidebar` to include the station list, and `--at 2026-09-30T12:00Z` to render what the frame would show at that UTC time.

## Find cameras with Osiris

[Osiris](https://github.com/simplifaisoul/osiris) aggregates ~17,000 public cameras behind `/api/cctv`. Use it as a **catalogue**, not a live dependency: pick cameras from it, then the frame fetches each agency's JPEG directly.

```bash
# in the osiris checkout
npm install && npm run dev            # serves http://localhost:3000

# in cctv_frame
python frame.py --list-osiris --near 37.5665,126.978 --radius 5 --probe   # Seoul
python frame.py --list-osiris --region uk --probe
python frame.py --list-osiris --region texas --limit 50
```

Add `--save` to probe the listed cameras and append the ones marked `[OK]` to `playlist.json` as stations.

Only still-image feeds are listed. HLS, YouTube, iframe and MJPEG streams are skipped. `--probe` fetches each listed feed and marks it `[OK]` only if it returns an image. 

Osiris's own fetcher (`src/lib/stealthFetch.ts`) spoofs residential IPs and browser fingerprints. This frame does not: it sends one honest User-Agent at a 60 s interval. Keep it that way.

## Run on the Raspberry Pi

1. Flash **Raspberry Pi OS (64-bit, with desktop)** with Raspberry Pi Imager. In its settings, set the hostname, Wi-Fi, and SSH.
2. `sudo apt install -y python3-pil python3-pil.imagetk python3-requests python3-tk git`
3. Clone this repo, then `cd cctv_frame && python3 frame.py --once` to confirm the camera works.
4. Turn off screen blanking: `sudo raspi-config` → Display Options → Screen Blanking → No.
5. Autostart on boot (Bookworm/labwc):
   ```bash
   mkdir -p ~/.config/labwc
   echo "python3 $HOME/hvac-gtm-pipeline/cctv_frame/frame.py &" >> ~/.config/labwc/autostart
   ```
   Enable desktop auto-login (`raspi-config` → System → Auto Login). After a power cut, the Pi then boots straight back into the frame.

## Config (`config.json`)

| Key | Default | Meaning |
|---|---|---|
| `image_url` | TfL JamCam | Used only if `playlist.json` is missing |
| `style` | `real` | Default style: `real` or `pixel` |
| `rotate_seconds` | 120 | Time on each station while scanning |
| `station_id_seconds` | 5 | How long the station ID stays up after tuning |
| `static_seconds` | 0.6 | Length of the static burst between stations |
| `sidebar_timeout_seconds` | 20 | The station list hides after this long with no input |
| `pixel.night_palette` | `night16` | Palette used in pixel mode when the station is in night |
| `pixel.width` | 128 | Target art-canvas width; snapped so a whole-number upscale fills the same area as `real`. Lower = chunkier (96 = very sprite-like, 160 = more detail) |
| `pixel.palette` | `city16` | `city16` (built for street cams: neutral grey ramp keeps roads grey), `db16` (muted, painterly; tints grey asphalt pink), `pico8` (saturated), `gameboy` (4 greens), `adaptive` (closest to the photo) |
| `pixel.colors` | 16 | Palette size, used only by `adaptive` |
| `pixel.dither` | `ordered` | `ordered` (Bayer pattern) or `none` (flat areas only) |
| `pixel.dither_strength` | 8 | Above ~12, flat sky turns into a checkerboard |
| `interval_seconds` | 60 | Fetch period. Most traffic cams update every 1–5 min, so faster is wasted |
| `image_scale` | 0.92 | Share of the screen the image fills. The rest is black margin that the mat hides |
| `brightness` | 0.85 | Dims the image so it reads as "behind glass" |
| `screen_width/height` | auto | Override if the display reports the wrong size |

## Assembly for the black-glass look

1. Measure the panel's **active area**, then cut the mat window 1–2 mm smaller on each side.
2. Stack the layers front to back: tinted acrylic (optional), mat, panel face-down. Put foam tape behind the panel.
3. Turn the panel's own backlight down, since a black level is only as good as its backlight bleed.
4. Route the cables out through a notch in the backboard, then clip the Pi to the backboard.

## Prototype 1 acceptance checklist

- [ ] Image refreshes on its own and matches the live camera
- [ ] Pulling Wi-Fi keeps the last image on screen with no error dialog
- [ ] Power-cycling the Pi boots back to fullscreen with no touching
- [ ] No visible bezel or backlight glow at the mat edge in a dim room
