"""Slide-in station list (the radio dial), drawn with Pillow onto the frame image.

Drawing into the image (instead of Tk widgets) keeps the display one fullscreen
picture, makes the UI testable headless, and looks identical on every OS.
Returns hitboxes so the Tk shell can map taps/clicks back to actions.
"""

from PIL import Image, ImageDraw, ImageFont

from playlist import cam_phase
from sun import local_time

FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Raspberry Pi OS, Debian
    "DejaVuSans.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
]
PHASE_GLYPH = {"day": "☀", "dusk": "◐", "night": "☾"}
INK = (232, 232, 226)
DIM = (130, 132, 136)
FAINT = (70, 72, 78)
ACCENT = (227, 207, 91)
OFFLINE = (208, 70, 72)

_font_cache = {}


def font(size):
    size = max(8, int(size))
    if size not in _font_cache:
        for path in FONT_PATHS:
            try:
                _font_cache[size] = ImageFont.truetype(path, size)
                break
            except OSError:
                continue
        else:
            _font_cache[size] = ImageFont.load_default()
    return _font_cache[size]


def _fit(draw, text, fnt, max_w):
    if draw.textlength(text, font=fnt) <= max_w:
        return text
    while text and draw.textlength(text + "…", font=fnt) > max_w:
        text = text[:-1]
    return text + "…"


def draw_sidebar(frame, rotator, style, selected, when, now, offline=()):
    """Draw the sidebar over `frame` (RGB, modified copy returned) + hitboxes.

    Hitboxes: list of (x0, y0, x1, y1, action) with action one of
    ("mode", name) | ("style", name) | ("pin", index).
    """
    W, H = frame.size
    sw = max(300, int(W * 0.34))
    x0 = W - sw
    img = frame.copy()
    shade = Image.new("RGB", (sw, H), (4, 5, 7))
    img.paste(Image.blend(img.crop((x0, 0, W, H)), shade, 0.86), (x0, 0))
    d = ImageDraw.Draw(img)
    d.line([(x0, 0), (x0, H)], fill=(38, 40, 46), width=1)

    u = H / 600  # scale unit
    pad = int(18 * u)
    x, y = x0 + pad, int(16 * u)
    inner = sw - 2 * pad
    boxes = []

    d.text((x, y), "VISUAL RADIO", font=font(12 * u), fill=DIM)
    y += int(24 * u)

    def chips(options, active, kind, y):
        cx = x
        for label, value in options:
            f = font(13 * u)
            w = int(d.textlength(label, font=f) + 16 * u)
            h = int(24 * u)
            on = value == active
            d.rounded_rectangle([cx, y, cx + w, y + h], radius=int(5 * u),
                                fill=(46, 48, 54) if on else None,
                                outline=(90, 92, 98) if on else FAINT)
            d.text((cx + 8 * u, y + 4 * u), label, font=f, fill=INK if on else DIM)
            boxes.append((cx, y, cx + w, y + h, (kind, value)))
            cx += w + int(6 * u)
        return y + h

    y = chips([("SCAN ☀", "auto"), ("SCAN ALL", "all"), ("TUNED", "pinned")],
              rotator.mode, "mode", y) + int(8 * u)
    y = chips([("REAL", "real"), ("PIXEL", "pixel")], style, "style", y) + int(14 * u)
    d.line([(x, y), (x + inner, y)], fill=FAINT)
    y += int(8 * u)

    row_h = int(46 * u)
    footer_h = int(52 * u)
    visible = max(1, (H - y - footer_h) // row_h)
    start = min(max(0, selected - visible // 2), max(0, len(rotator.cams) - visible))
    pool = set(rotator.eligible(when))
    for i in range(start, min(len(rotator.cams), start + visible)):
        cam = rotator.cams[i]
        ph = cam_phase(cam, when)
        is_cur, is_sel = i == rotator.index, i == selected
        dead = cam["id"] in offline
        if is_sel:
            d.rectangle([x0 + 1, y, W, y + row_h - 2], fill=(28, 30, 36))
        if is_cur:
            d.rectangle([x0 + 1, y, x0 + int(4 * u), y + row_h - 2], fill=ACCENT)
        name_col = INK if (i in pool and not dead) else DIM
        nf, sf = font(15 * u), font(12 * u)
        d.text((x, y + 6 * u), _fit(d, cam["name"], nf, inner - 30 * u), font=nf, fill=name_col)
        d.text((x0 + sw - pad - 18 * u, y + 5 * u), PHASE_GLYPH[ph], font=font(16 * u),
               fill=ACCENT if ph == "day" else DIM)
        where = cam.get("city") or cam.get("country") or ""
        t = local_time(cam["lng"], when, cam.get("tz")) if cam.get("lng") is not None else ""
        sub = " · ".join(p for p in (where, t, "offline" if dead else ph) if p)
        d.text((x, y + 26 * u), _fit(d, sub, sf, inner), font=sf, fill=OFFLINE if dead else DIM)
        boxes.append((x0, y, W, y + row_h, ("pin", i)))
        y += row_h

    fy = H - footer_h + int(6 * u)
    d.line([(x, fy - 6 * u), (x + inner, fy - 6 * u)], fill=FAINT)
    left = rotator.seconds_left(now)
    status = "tuned · holding this station" if left is None else f"scanning · next station in {left // 60}:{left % 60:02d}"
    d.text((x, fy), status, font=font(12 * u), fill=DIM)
    d.text((x, fy + 18 * u), "←→ tune  ↑↓ select  ⏎ hold  A scan  P style  S hide",
           font=font(11 * u), fill=FAINT)
    return img, boxes
