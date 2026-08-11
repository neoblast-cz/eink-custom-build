"""Shared Material Design 3 grayscale theme for e-ink modules.

M3 is a color-driven design language; there's no color on this display, so
"tone" here means a grayscale value standing in for an M3 surface/color role.
Fills (cards, chips, progress tracks) can safely use light tones — they
dither into a visible stipple on the real 1-bit panel. Thin 1px strokes and
small text need to stay closer to black or they fuzz out under dithering.
"""

from PIL import ImageFont

# ── Tonal palette ──────────────────────────────────────────────────

SURFACE = 255
SURFACE_CONTAINER_LOW = 248
SURFACE_CONTAINER = 240
SURFACE_CONTAINER_HIGH = 230
SURFACE_CONTAINER_HIGHEST = 220
SELECTED = SURFACE_CONTAINER_HIGHEST

OUTLINE = 200          # the only stroke tone — dividers, card outlines
ON_SURFACE = 0          # primary text, icons, emphasis fills
ON_SURFACE_VARIANT = 100  # secondary text (≥13px only — see module docstring)
DISABLED = 150          # muted/ghost text

# ── Shape scale ────────────────────────────────────────────────────

RADIUS_XS = 4
RADIUS_SM = 8
RADIUS_MD = 12
RADIUS_LG = 16
RADIUS_XL = 28

# ── Spacing scale (8dp grid) ───────────────────────────────────────

SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 16
SPACE_XL = 24
SPACE_XXL = 32

# ── Type scale ─────────────────────────────────────────────────────

_FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]

_TYPE_SCALE = [
    ("display", 42),
    ("headline", 28),
    ("title", 20),
    ("body_lg", 16),
    ("body", 14),
    ("label", 12),
    ("label_sm", 10),
]

_font_cache: dict = {}


def load_fonts() -> dict:
    """Named font scale, cached per-process (one filesystem probe, not one per render)."""
    if _font_cache:
        return _font_cache

    for name, size in _TYPE_SCALE:
        loaded = False
        for path in _FONT_PATHS:
            try:
                _font_cache[name] = ImageFont.truetype(path, size)
                loaded = True
                break
            except OSError:
                continue
        if not loaded:
            _font_cache[name] = ImageFont.load_default()
    return _font_cache


# ── Shape helpers ──────────────────────────────────────────────────

def clamp_radius(radius: int, w: float, h: float) -> int:
    """Keep a corner radius from exceeding half of either box dimension —
    Pillow silently degrades an over-large radius into a plain ellipse
    (pinched corners) rather than the intended stadium/rounded-rect shape."""
    return max(1, min(int(radius), int(w) // 2, int(h) // 2))


def draw_card(draw, box, radius=RADIUS_LG, fill=SURFACE_CONTAINER, outline=None, outline_width=1):
    """A rounded 'surface container' panel — the basic M3 card."""
    x0, y0, x1, y1 = box
    r = clamp_radius(radius, x1 - x0, y1 - y0)
    if outline:
        draw.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=fill, outline=outline, width=outline_width)
    else:
        draw.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=fill)


def draw_divider(draw, x0, y, x1, tone=OUTLINE, width=1):
    draw.line([(x0, y), (x1, y)], fill=tone, width=width)


def draw_chip(draw, anchor_xy, text, font, *,
              align="left", valign="top",
              fill=SURFACE_CONTAINER_HIGH, text_fill=ON_SURFACE, outline=None,
              pad_x=SPACE_SM, pad_y=4, min_height=18):
    """A small pill-shaped label — M3's 'assist chip'. Anchored at a point
    (not a literal box) since every current call site already has a single
    x or y to hang it from (a right-aligned column, a row's y). Always a
    true pill regardless of text length. Returns the drawn (x0,y0,x1,y1)
    box so callers can lay out whatever sits next to it."""
    ax, ay = anchor_xy
    bbox = font.getbbox(text)
    text_h = bbox[3] - bbox[1]
    text_w = font.getlength(text)

    box_w = text_w + pad_x * 2
    box_h = max(min_height, text_h + pad_y * 2)

    if align == "right":
        x0 = ax - box_w
    elif align == "center":
        x0 = ax - box_w / 2
    else:
        x0 = ax

    if valign == "center":
        y0 = ay - box_h / 2
    elif valign == "bottom":
        y0 = ay - box_h
    else:
        y0 = ay

    x1, y1 = x0 + box_w, y0 + box_h
    radius = clamp_radius(box_h, box_w, box_h)  # true pill: half the box height

    if outline:
        draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=fill, outline=outline, width=1)
    else:
        draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=fill)

    text_x = x0 + pad_x
    text_y = y0 + (box_h - text_h) / 2 - bbox[1]
    draw.text((text_x, text_y), text, fill=text_fill, font=font)

    return (x0, y0, x1, y1)


def truncate_to_width(text, font, max_width, ellipsis="…"):
    """Shorten text with a trailing ellipsis until it fits max_width."""
    if font.getlength(text) <= max_width:
        return text
    while text and font.getlength(text + ellipsis) > max_width:
        text = text[:-1]
    return (text + ellipsis) if text else ellipsis


def draw_empty_state(draw, width, height, title, hint=None, fonts=None):
    """Consistent 'no data' / 'not authorized' screen, centered on the canvas."""
    if fonts is None:
        fonts = load_fonts()
    cx, cy = width // 2, height // 2

    tw = fonts["title"].getlength(title)
    draw.text((cx - tw / 2, cy - 20), title, fill=ON_SURFACE, font=fonts["title"])

    if hint:
        hw = fonts["body"].getlength(hint)
        draw.text((cx - hw / 2, cy + 14), hint, fill=DISABLED, font=fonts["body"])


# ── Icons ──────────────────────────────────────────────────────────
# Simple monochrome silhouettes drawn with PIL primitives — no icon font or
# asset dependency. Keep them single-tone: at 20-28px on a dithered 1-bit
# display, internal shading just turns to noise.

def _icon_footsteps(draw, box, tone, bg):
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    # back foot (larger, bottom-left)
    fw, fh = bw * 0.45, bh * 0.65
    draw.ellipse([x0, y0 + bh - fh, x0 + fw, y1], fill=tone)
    # front foot (smaller, top-right), offset to suggest a stride
    fw2, fh2 = bw * 0.4, bh * 0.55
    draw.ellipse([x1 - fw2, y0, x1, y0 + fh2], fill=tone)


def _icon_pin(draw, box, tone, bg):
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    cx = (x0 + x1) / 2
    head_r = w * 0.32
    head_cy = y0 + head_r + h * 0.05
    draw.ellipse([cx - head_r, head_cy - head_r, cx + head_r, head_cy + head_r], fill=tone)
    draw.polygon(
        [(cx - head_r * 0.75, head_cy + head_r * 0.4),
         (cx + head_r * 0.75, head_cy + head_r * 0.4),
         (cx, y1)],
        fill=tone,
    )
    hole_r = head_r * 0.4
    draw.ellipse([cx - hole_r, head_cy - hole_r, cx + hole_r, head_cy + hole_r], fill=bg)


def _icon_flame(draw, box, tone, bg):
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    cx = (x0 + x1) / 2
    draw.polygon(
        [(cx, y0),
         (cx + w * 0.28, y0 + h * 0.35),
         (cx + w * 0.38, y0 + h * 0.65),
         (cx + w * 0.22, y1),
         (cx - w * 0.22, y1),
         (cx - w * 0.38, y0 + h * 0.65),
         (cx - w * 0.20, y0 + h * 0.4)],
        fill=tone,
    )


def _icon_moon(draw, box, tone, bg):
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    draw.ellipse([x0, y0, x1, y1], fill=tone)
    cut_r = w * 0.55
    cut_cx = x0 + w * 0.62
    cut_cy = y0 + h * 0.38
    draw.ellipse([cut_cx - cut_r, cut_cy - cut_r, cut_cx + cut_r, cut_cy + cut_r], fill=bg)


_ICONS = {
    "footsteps": _icon_footsteps,
    "pin": _icon_pin,
    "flame": _icon_flame,
    "moon": _icon_moon,
}


def draw_icon(draw, glyph: str, xy, size=24, *, tone=ON_SURFACE, bg=SURFACE, anchor="tl"):
    x, y = xy
    if anchor == "center":
        box = (x - size / 2, y - size / 2, x + size / 2, y + size / 2)
    else:
        box = (x, y, x + size, y + size)
    fn = _ICONS.get(glyph)
    if fn:
        fn(draw, box, tone, bg)
