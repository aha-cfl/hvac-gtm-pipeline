"""
Pixel-art ("sprite") renderer: turns a camera photo into an Aseprite-style image.

Pipeline: punch up contrast/saturation -> area-average down to a small canvas
-> light ordered (Bayer) dither -> snap to a limited palette. Upscaling happens later, with nearest-neighbor
at an integer factor, so every art pixel stays a crisp square.
"""

from PIL import Image, ImageEnhance

# Well-known pixel-art palettes (hex, darkest-ish first).
PALETTES = {
    "db16": [  # DawnBringer 16: muted, painterly, good all-rounder for photos
        "140c1c", "442434", "30346d", "4e4a4e", "854c30", "346524", "d04648", "757161",
        "597dce", "d27d2c", "8595a1", "6daa2c", "d2aa99", "6dc2ca", "dad45e", "deeed6",
    ],
    "pico8": [  # PICO-8: saturated, playful
        "000000", "1d2b53", "7e2553", "008751", "ab5236", "5f574f", "c2c3c7", "fff1e8",
        "ff004d", "ffa300", "ffec27", "00e436", "29adff", "83769c", "ff77a8", "ffccaa",
    ],
    "gameboy": ["0f380f", "306230", "8bac0f", "9bbc0f"],  # DMG green, 4 shades
    "city16": [  # Built for street cams: 8-step grey ramp (cool shadows -> warm
                 # highlights) so asphalt/concrete stay neutral, plus foliage,
                 # sky/glass, brick, sodium-amber, brake-light red, taxi yellow.
        "0e0f14", "22252e", "3a3e48", "575c66", "7a7f87", "a1a5aa", "c9cbcb", "eeeee6",
        "34552f", "6f9447", "3f6a8f", "8fb6d0", "8a4b3a", "d49a3e", "d04648", "e3cf5b",
    ],
}

# 4x4 Bayer matrix, values 0..15.
BAYER4 = [
    [0, 8, 2, 10],
    [12, 4, 14, 6],
    [3, 11, 1, 9],
    [15, 7, 13, 5],
]

DEFAULTS = {
    "width": 128,           # art-canvas width in pixels; height follows aspect
    "palette": "city16",    # city16 | db16 | pico8 | gameboy | adaptive
    "colors": 16,           # only used by "adaptive"
    "dither": "ordered",    # ordered | none
    "dither_strength": 8,   # +/- RGB spread; >12 turns flat areas into checkerboard
    "contrast": 1.15,
    "saturation": 1.25,
}


def _palette_image(hex_colors):
    flat = []
    for h in hex_colors:
        flat += [int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)]
    # Pad by repeating the first color so padding never wins a nearest match
    # over a real entry that is equally close.
    flat += flat[:3] * (256 - len(hex_colors))
    pal = Image.new("P", (1, 1))
    pal.putpalette(flat)
    return pal


def _ordered_dither(img, strength):
    """Add a tiled Bayer offset so flat gradients break into clean patterns."""
    w, h = img.size
    src = img.load()
    out = Image.new("RGB", (w, h))
    dst = out.load()
    for y in range(h):
        row = BAYER4[y % 4]
        for x in range(w):
            off = int((row[x % 4] / 15.0 - 0.5) * 2 * strength)
            r, g, b = src[x, y]
            dst[x, y] = (
                min(255, max(0, r + off)),
                min(255, max(0, g + off)),
                min(255, max(0, b + off)),
            )
    return out


def pixelate(img, settings=None):
    """Return a small RGB pixel-art image (not upscaled)."""
    s = {**DEFAULTS, **(settings or {})}
    img = img.convert("RGB")
    img = ImageEnhance.Contrast(img).enhance(s["contrast"])
    img = ImageEnhance.Color(img).enhance(s["saturation"])

    w = max(8, int(s["width"]))
    h = max(8, round(w * img.height / img.width))
    small = img.resize((w, h), Image.BOX)  # area average: no shimmer or aliasing

    if s["dither"] == "ordered":
        small = _ordered_dither(small, s["dither_strength"])

    if s["palette"] == "adaptive":
        small = small.quantize(colors=int(s["colors"]), method=Image.Quantize.MEDIANCUT,
                               dither=Image.Dither.NONE).convert("RGB")
    else:
        if s["palette"] not in PALETTES:
            raise ValueError(f"unknown palette {s['palette']!r}; "
                             f"choose from {sorted(PALETTES) + ['adaptive']}")
        pal = _palette_image(PALETTES[s["palette"]])
        small = small.quantize(palette=pal, dither=Image.Dither.NONE).convert("RGB")

    return small
