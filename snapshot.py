#!/usr/bin/env python3
"""Generate a PNG snapshot of current FT8 spots from the SQLite spot store."""

import io
import json
import math
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

import requests_cache
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from staticmap import IconMarker, StaticMap
import staticmap.staticmap as _sm

# staticmap's _lon_to_x normalises any lon outside [-180,180) back into that
# range, breaking world-wrap for Japan-centred maps where pre-normalised
# longitudes like 260° (US) must be passed through unchanged.
_sm._lon_to_x = lambda lon, zoom: ((lon + 180.0) / 360.0) * pow(2, zoom)

DB_PATH = Path(__file__).parent / "data" / "spots.db"
OUT_DIR = Path(__file__).parent / "data" / "timelapse"
TILE_CACHE_PATH = Path(__file__).parent / "data" / "tile_cache"

# Install a persistent requests cache so OSM tiles are only downloaded once.
# expire_after=-1 means cached forever (map tiles at zoom 3 never change).
requests_cache.install_cache(str(TILE_CACHE_PATH), expire_after=-1)

# Matches map-ui.js COLOR_MAP; key = band integer (strip "m" suffix)
BAND_COLORS = {
    160: "#332288",
    80:  "#882255",
    40:  "#117733",
    30:  "#CC3311",
    20:  "#0077BB",
    17:  "#EE3377",
    15:  "#CC6677",
    12:  "#009E73",
    10:  "#0099CC",
    6:   "#AA9900",
    2:   "#E69F00",
    0:   "#888888",
}

# Matches map-ui.js BAND_CUES
BAND_CUES = {
    160: "-", 80: "|", 40: "/", 30: "\\", 20: "x",
    17: "", 15: "x", 12: "\\", 10: "/", 6: "|", 2: "-", 0: "",
}

# Matches map-ui.js BAND_CUE_COLORS
BAND_CUE_COLORS = {
    160: "#fff", 80: "#fff", 40: "#fff", 30: "#fff", 20: "#fff", 17: "#fff",
    15: "#000", 12: "#000", 10: "#000", 6: "#000", 2: "#000", 0: "#fff",
}

TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
ICON_SIZE = 22   # matches web app SVG size

# Map viewport: Japan (135°E) centered; opposite longitude (45°W) at both edges.
# zoom=3 → tile world = 256×2³ = 2048 px wide = exactly 360° longitude.
# Height is derived so the map covers 75°N to 60°S (all major landmasses).
MAP_ZOOM = 3
# Cut falls at 30°W (open Atlantic), Iceland and SA both intact
MAP_CENTER_LON = 150


def _mercator_y(lat_deg: float) -> float:
    r = math.radians(lat_deg)
    return math.log(math.tan(math.pi / 4 + r / 2))


_LAT_TOP = 75.0   # northernmost latitude to show
_LAT_BOTTOM = -60.0   # southernmost latitude to show
_PX_PER_MERCATOR = (256 * 2 ** MAP_ZOOM) / \
    (2 * math.pi)  # ≈ 325.9 px per mercator unit
_Y_TOP = _mercator_y(_LAT_TOP)
_Y_BOTTOM = _mercator_y(_LAT_BOTTOM)
MAP_CENTER_LAT = math.degrees(
    2 * math.atan(math.exp((_Y_TOP + _Y_BOTTOM) / 2)) - math.pi / 2)

# = 2048 (exactly 360°)
WIDTH = 256 * 2 ** MAP_ZOOM
HEIGHT = round((_Y_TOP - _Y_BOTTOM) * _PX_PER_MERCATOR)  # ≈ 1090


def _hex_to_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _halo_line(draw: ImageDraw.ImageDraw, x1, y1, x2, y2, color: str):
    """Draw a line with contrasting halo, matching ws-client.js haloLine()."""
    halo = "#000" if color == "#fff" else "#fff"
    draw.line([(x1, y1), (x2, y2)], fill=halo, width=4)
    draw.line([(x1, y1), (x2, y2)], fill=color, width=2)


def _draw_cue(draw: ImageDraw.ImageDraw, cue_key: str, color: str):
    """Draw band cue line(s) matching CUE_SVG in ws-client.js (center 11,11)."""
    if cue_key == "-":
        _halo_line(draw, 7, 11, 15, 11, color)
    elif cue_key == "|":
        _halo_line(draw, 11, 7, 11, 15, color)
    elif cue_key == "/":
        _halo_line(draw, 7, 15, 15, 7, color)
    elif cue_key == "\\":
        _halo_line(draw, 7, 7, 15, 15, color)
    elif cue_key == "x":
        _halo_line(draw, 7, 15, 15, 7, color)
        _halo_line(draw, 7, 7, 15, 15, color)


def _make_icon(band_int: int) -> bytes:
    """Render a 22×22 RGBA circle marker matching the web app appearance."""
    color = BAND_COLORS.get(band_int, BAND_COLORS[0])
    cue_key = BAND_CUES.get(band_int, "")
    cue_color = BAND_CUE_COLORS.get(band_int, "#fff")

    img = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Circle: cx=11 cy=11 r=9.5 fill=color stroke=white 1.5 (matches SVG shape 0)
    draw.ellipse([1, 1, 20, 20], fill=_hex_to_rgb(color) +
                 (255,), outline=(255, 255, 255, 255), width=2)

    if cue_key:
        _draw_cue(draw, cue_key, cue_color)

    # Dot for band 17
    if band_int == 17:
        draw.ellipse([8, 8, 14, 14], fill=(0, 0, 0, 255))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# Cache PNG bytes by band; each call to _get_icon returns a fresh BytesIO so
# that multiple IconMarkers of the same band don't share a single file pointer.
_icon_cache: dict[int, bytes] = {}


def _get_icon(band_int: int) -> io.BytesIO:
    if band_int not in _icon_cache:
        _icon_cache[band_int] = _make_icon(band_int)
    return io.BytesIO(_icon_cache[band_int])


def _subsolar_point(dt: datetime) -> tuple[float, float]:
    """Return (declination_rad, lon_rad) of the subsolar point for UTC datetime."""
    J2000 = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    n = (dt - J2000).total_seconds() / 86400.0
    L = (280.460 + 0.9856474 * n) % 360
    g = math.radians((357.528 + 0.9856003 * n) % 360)
    lam = math.radians(L + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g))
    eps = math.radians(23.439 - 0.0000004 * n)
    dec = math.asin(math.sin(eps) * math.sin(lam))
    ra = math.atan2(math.cos(eps) * math.sin(lam), math.cos(lam))
    gmst = (280.46061837 + 360.98564736629 * n) % 360
    lon_sun = ((-(gmst - math.degrees(ra)) + 180) % 360) - 180
    return dec, math.radians(lon_sun)


def _draw_night_overlay(image: Image.Image, dt: datetime) -> Image.Image:
    """Overlay the night side as a semi-transparent dark area using numpy."""
    dec, lon_sun = _subsolar_point(dt)
    w, h = image.size

    # Pixel → longitude (radians)
    x_center_tiles = (MAP_CENTER_LON + 180.0) / 360.0 * (2 ** MAP_ZOOM)
    tile_x = x_center_tiles - w / (2 * 256) + np.arange(w) / 256.0
    lon = np.radians(tile_x / (2 ** MAP_ZOOM) * 360 - 180)  # shape (w,)

    # Pixel → latitude (radians) via inverse Mercator
    y_center_tiles = (1 - _mercator_y(MAP_CENTER_LAT) /
                      math.pi) / 2 * (2 ** MAP_ZOOM)
    tile_y = y_center_tiles - h / (2 * 256) + np.arange(h) / 256.0
    merc_y = math.pi * (1 - 2 * tile_y / (2 ** MAP_ZOOM))
    lat = 2 * np.arctan(np.exp(merc_y)) - math.pi / 2  # shape (h,)

    # cos(solar zenith) < 0 → night
    cos_zenith = (np.sin(lat)[:, None] * math.sin(dec) +
                  np.cos(lat)[:, None] * math.cos(dec) * np.cos(lon[None, :] - lon_sun))
    night = cos_zenith < 0  # shape (h, w)

    overlay = np.zeros((h, w, 4), dtype=np.uint8)
    overlay[night] = [0, 0, 20, 40]   # dark blue, semi-transparent
    result = Image.alpha_composite(image.convert("RGBA"),
                                   Image.fromarray(overlay, "RGBA"))
    return result.convert("RGB")


def _band_int(b: str) -> int:
    try:
        return int(str(b).replace("m", ""))
    except ValueError:
        return 0


def _draw_timestamp(image: Image.Image, dt: datetime) -> None:
    """Draw UTC date and time at the bottom-left corner of the image (in-place)."""
    label = dt.strftime("%Y-%m-%d  %H:%M") + " UTC"
    try:
        font = ImageFont.truetype("/usr/share/fonts/ttf-dejavu/DejaVuSans-Bold.ttf", 42)
    except OSError:
        font = ImageFont.load_default(size=42)
    draw = ImageDraw.Draw(image)
    x, y = 12, image.height - 58
    # Semi-transparent dark background pill for guaranteed contrast
    bbox = draw.textbbox((x, y), label, font=font)
    pad = 6
    draw.rounded_rectangle(
        [bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad],
        radius=6, fill=(0, 0, 0, 180),
    )
    draw.text((x, y), label, font=font, fill=(255, 255, 255, 255))


def generate_snapshot(out_path: Path | None = None, mode: str = "from_jp") -> Path:
    now = datetime.now(timezone.utc)
    if out_path is None:
        day_dir = OUT_DIR / now.strftime("%Y-%m-%d")
        day_dir.mkdir(parents=True, exist_ok=True)
        out_path = day_dir / now.strftime("%H-%M.png")

    db = sqlite3.connect(str(DB_PATH))
    cutoff = time.time() - 180
    rows = db.execute(
        "SELECT payload FROM spots WHERE ts >= ? ORDER BY ts ASC", (cutoff,)
    ).fetchall()
    db.close()

    half = ICON_SIZE // 2
    m = StaticMap(WIDTH, HEIGHT, url_template=TILE_URL)
    added = 0
    for row in rows:
        try:
            spot = json.loads(row[0])
            if spot.get("mode") != mode:
                continue
            lon, lat = spot.get("lon"), spot.get("lat")
            if lon is None or lat is None:
                continue
            # Shift lon into the ±180° window around the map centre.
            lon = MAP_CENTER_LON + \
                ((lon - MAP_CENTER_LON + 180 + 360) % 360 - 180)
            band = _band_int(spot.get("b", ""))
            icon = _get_icon(band if band in BAND_COLORS else 0)
            m.add_marker(IconMarker((lon, lat), icon, half, half))
            added += 1
        except Exception:
            continue

    if added == 0:
        # No spots — add a transparent 1×1 marker so staticmap can still render tiles
        dot = io.BytesIO()
        Image.new("RGBA", (1, 1), (0, 0, 0, 0)).save(dot, format="PNG")
        dot.seek(0)
        m.add_marker(IconMarker((0, 0), dot, 0, 0))

    image = m.render(zoom=MAP_ZOOM, center=(MAP_CENTER_LON, MAP_CENTER_LAT))
    image = _draw_night_overlay(image, now)
    _draw_timestamp(image, now)
    image.save(str(out_path))
    print(
        f"[snapshot] {out_path.name}  mode={mode}  spots={added}", flush=True)
    return out_path


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate FT8 spot snapshot")
    parser.add_argument("--mode", choices=["from_jp", "to_jp"], default="from_jp",
                        help="Spot direction to plot (default: from_jp)")
    args = parser.parse_args()
    generate_snapshot(mode=args.mode)
