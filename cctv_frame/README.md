# cctv_frame — black-glass CCTV frame

One public traffic camera, fullscreen, centered on pure black, refreshed every 60 s.
If the feed fails, it keeps showing the last good image, and that image survives reboots.

**Two styles** (Prototype 2):

| Style | Look | For |
|---|---|---|
| `pixel` (default) | Aseprite-style sprite art: 128 px wide, 16-color palette, crisp square pixels | Ambient art; also the privacy layer |
| `real` | The camera image as-is | People who want the actual live view |

Press **P** or **Space** to switch styles. The choice is saved, so it survives reboots.
Which style shows is decided in this order: `--style` flag, then the last toggle on this device, then `style` in `config.json`.

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
python frame.py                       # fullscreen; P/Space toggles style, Esc quits
```

`python frame.py --preview any_photo.jpg` writes `cache/preview.png` with the two styles side by side, without any network. Use it to tune the pixel settings.

`python frame.py --once` renders a single frame to `cache/latest.png` without opening a window. Use it to check a camera URL.

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
| `image_url` | TfL JamCam | Direct JPEG snapshot URL |
| `style` | `pixel` | Default style: `pixel` or `real` |
| `pixel.width` | 128 | Art-canvas width. Lower = chunkier (96 = very sprite-like, 160 = more detail) |
| `pixel.palette` | `db16` | `db16` (muted, painterly), `pico8` (saturated), `gameboy` (4 greens), `adaptive` (closest to the photo) |
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
