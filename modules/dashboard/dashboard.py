import math
import logging
from io import BytesIO
from datetime import datetime
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont
from modules.base import BaseModule

logger = logging.getLogger(__name__)

MESSAGE_FONT_SIZES = {
    "small": 16,
    "medium": 22,
    "large": 30,
    "extra-large": 40,
}

AQI_LEVELS = [
    (20, "Excellent", 220),
    (40, "Good", 190),
    (60, "Moderate", 150),
    (80, "Poor", 110),
    (100, "Very Poor", 70),
    (999, "Hazardous", 30),
]


class DashboardModule(BaseModule):
    NAME = "dashboard"
    DISPLAY_NAME = "Dashboard"
    DESCRIPTION = "Affirmations, weather/AQI, and precipitation radar"

    def render(self, width: int, height: int, settings: dict) -> Image.Image:
        img = Image.new("L", (width, height), 255)
        draw = ImageDraw.Draw(img)
        fonts = self._load_fonts()

        mid_x = width // 2
        mid_y = height // 2

        # Vertical divider (full height)
        draw.line([(mid_x, 10), (mid_x, height - 10)], fill=180, width=1)
        # Horizontal divider (left side only)
        draw.line([(10, mid_y), (mid_x - 10, mid_y)], fill=180, width=1)

        # Top-left: Daily affirmation
        affirmation = self._fetch_affirmation()
        font_size_name = settings.get("message_font", "medium")
        self._draw_message(draw, 0, 0, mid_x, mid_y, affirmation, font_size_name, fonts)

        # Bottom-left: Weather + AQI
        weather = self._fetch_weather(settings.get("weather_location", ""))
        aqi = self._fetch_aqi(settings.get("latitude", ""), settings.get("longitude", ""))
        self._draw_weather_aqi(draw, 0, mid_y, mid_x, height, weather, aqi, fonts)

        # Right side (full height): Precipitation radar
        radar_img, radar_meta = self._fetch_radar(settings.get("latitude", ""), settings.get("longitude", ""))
        self._draw_radar(img, draw, mid_x, 0, width, height, radar_img, radar_meta, fonts)

        return img

    def default_settings(self) -> dict:
        return {
            "weather_location": "",
            "latitude": "",
            "longitude": "",
            "message_font": "medium",
        }

    def _load_fonts(self):
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "C:/Windows/Fonts/segoeuib.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]
        fonts = {}
        sizes = [("xxl", 56), ("xl", 40), ("lg", 30), ("md", 22), ("sm", 16), ("xs", 13)]
        for size_name, size in sizes:
            loaded = False
            for path in font_paths:
                try:
                    fonts[size_name] = ImageFont.truetype(path, size)
                    loaded = True
                    break
                except OSError:
                    continue
            if not loaded:
                fonts[size_name] = ImageFont.load_default()
        return fonts

    # ── Affirmation (top-left) ───────────────────────────────────────

    def _fetch_affirmation(self) -> str:
        try:
            import requests
            resp = requests.get("https://www.affirmations.dev", timeout=10)
            resp.raise_for_status()
            return resp.json().get("affirmation", "You are doing great!")
        except Exception as e:
            logger.error(f"Affirmation fetch failed: {e}")
            return "You are doing great!"

    def _draw_message(self, draw, x1, y1, x2, y2, message, font_size_name, fonts):
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        max_w = x2 - x1 - 40

        size = MESSAGE_FONT_SIZES.get(font_size_name, 22)
        font_key = {16: "sm", 22: "md", 30: "lg", 40: "xl"}.get(size, "md")
        font = fonts[font_key]

        lines = self._wrap_text(message, font, max_w)

        # Cap lines to fit the quadrant height
        line_h = size + 6
        max_lines = max(1, (y2 - y1 - 20) // line_h)
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            lines[-1] = lines[-1].rstrip() + "..."

        total_h = len(lines) * line_h
        start_y = cy - total_h // 2

        for i, line in enumerate(lines):
            lw = font.getlength(line)
            draw.text((cx - lw // 2, start_y + i * line_h), line, fill=0, font=font)

    # ── Weather + AQI (bottom-left) ──────────────────────────────────

    def _fetch_weather(self, location: str) -> dict:
        if not location:
            return {}
        try:
            import requests
            resp = requests.get(
                f"https://wttr.in/{location}",
                params={"format": "j1"},
                headers={"User-Agent": "curl"},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            current = data["current_condition"][0]
            return {
                "temp_c": current["temp_C"],
                "feels_like": current.get("FeelsLikeC", ""),
                "humidity": current.get("humidity", ""),
                "condition": current["weatherDesc"][0]["value"],
                "weather_code": int(current.get("weatherCode", 0)),
                "location": location,
            }
        except Exception as e:
            logger.error(f"Weather fetch failed: {e}")
            return {}

    def _fetch_aqi(self, latitude: str, longitude: str) -> dict:
        if not latitude or not longitude:
            return {}
        try:
            import requests
            resp = requests.get(
                "https://air-quality-api.open-meteo.com/v1/air-quality",
                params={
                    "latitude": latitude,
                    "longitude": longitude,
                    "current": "european_aqi",
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            aqi_value = data.get("current", {}).get("european_aqi")
            if aqi_value is None:
                return {}

            aqi_int = int(aqi_value)
            label = "Unknown"
            shade = 150
            for threshold, lbl, sh in AQI_LEVELS:
                if aqi_int <= threshold:
                    label, shade = lbl, sh
                    break

            return {"value": aqi_int, "label": label, "shade": shade}
        except Exception as e:
            logger.error(f"AQI fetch failed: {e}")
            return {}

    def _draw_weather_icon(self, draw, cx, cy, code, size=40):
        """Draw a simple weather icon based on wttr.in weather code."""
        r = size // 2

        # Classify weather code into icon type
        # wttr.in codes: 113=sunny, 116=partly cloudy, 119/122=cloudy/overcast,
        # 176/263/266/293/296/299/302/305/308=rain variants,
        # 179/227/230/323/326/329/332/335/338=snow, 200/386/389=thunder
        if code == 113:
            # Sun: circle with rays
            draw.ellipse([cx - r // 2, cy - r // 2, cx + r // 2, cy + r // 2],
                          outline=0, width=2)
            for angle in range(0, 360, 45):
                rad = math.radians(angle)
                inner = r // 2 + 4
                outer = r - 2
                draw.line([(cx + inner * math.cos(rad), cy + inner * math.sin(rad)),
                           (cx + outer * math.cos(rad), cy + outer * math.sin(rad))],
                          fill=0, width=2)
        elif code in (116, 119):
            # Partly cloudy / cloudy: cloud shape
            draw.ellipse([cx - r, cy - 4, cx - r + 20, cy + 12], outline=0, width=2)
            draw.ellipse([cx - 8, cy - 14, cx + 14, cy + 8], outline=0, width=2)
            draw.ellipse([cx + 2, cy - 6, cx + r, cy + 14], outline=0, width=2)
            draw.line([(cx - r + 2, cy + 12), (cx + r - 2, cy + 12)], fill=0, width=2)
        elif code == 122:
            # Overcast: filled cloud
            draw.ellipse([cx - r, cy - 4, cx - r + 20, cy + 12], fill=160, outline=120, width=1)
            draw.ellipse([cx - 8, cy - 14, cx + 14, cy + 8], fill=160, outline=120, width=1)
            draw.ellipse([cx + 2, cy - 6, cx + r, cy + 14], fill=160, outline=120, width=1)
            draw.rectangle([cx - r + 10, cy, cx + r - 10, cy + 12], fill=160)
        elif code in (176, 263, 266, 293, 296, 299, 302, 305, 308):
            # Rain: cloud + droplets
            draw.ellipse([cx - 14, cy - 14, cx + 2, cy - 2], fill=180, outline=120, width=1)
            draw.ellipse([cx - 4, cy - 20, cx + 14, cy - 2], fill=180, outline=120, width=1)
            draw.rectangle([cx - 12, cy - 6, cx + 12, cy - 2], fill=180)
            # Raindrops
            for dx in [-8, 0, 8]:
                drop_x = cx + dx
                draw.line([(drop_x, cy + 4), (drop_x - 2, cy + 12)], fill=80, width=2)
                draw.line([(drop_x + 4, cy + 8), (drop_x + 2, cy + 16)], fill=80, width=2)
        elif code in (179, 227, 230, 323, 326, 329, 332, 335, 338):
            # Snow: cloud + snowflakes
            draw.ellipse([cx - 14, cy - 14, cx + 2, cy - 2], fill=200, outline=140, width=1)
            draw.ellipse([cx - 4, cy - 20, cx + 14, cy - 2], fill=200, outline=140, width=1)
            draw.rectangle([cx - 12, cy - 6, cx + 12, cy - 2], fill=200)
            # Snowflakes (small asterisks)
            for dx, dy in [(-8, 8), (2, 14), (10, 6)]:
                sx, sy = cx + dx, cy + dy
                for angle in [0, 60, 120]:
                    rad = math.radians(angle)
                    draw.line([(sx - 3 * math.cos(rad), sy - 3 * math.sin(rad)),
                               (sx + 3 * math.cos(rad), sy + 3 * math.sin(rad))], fill=60, width=1)
        elif code in (200, 386, 389, 392, 395):
            # Thunder: cloud + lightning bolt
            draw.ellipse([cx - 14, cy - 16, cx + 2, cy - 4], fill=140, outline=80, width=1)
            draw.ellipse([cx - 4, cy - 22, cx + 14, cy - 4], fill=140, outline=80, width=1)
            draw.rectangle([cx - 12, cy - 8, cx + 12, cy - 4], fill=140)
            # Lightning bolt
            draw.polygon([(cx - 2, cy), (cx + 4, cy + 8), (cx + 1, cy + 8),
                          (cx + 4, cy + 18), (cx - 4, cy + 8), (cx - 1, cy + 8)], fill=0)
        else:
            # Default: simple cloud
            draw.ellipse([cx - r, cy - 4, cx - r + 20, cy + 12], outline=100, width=2)
            draw.ellipse([cx - 8, cy - 14, cx + 14, cy + 8], outline=100, width=2)
            draw.ellipse([cx + 2, cy - 6, cx + r, cy + 14], outline=100, width=2)
            draw.line([(cx - r + 2, cy + 12), (cx + r - 2, cy + 12)], fill=100, width=2)

    def _draw_weather_aqi(self, draw, x1, y1, x2, y2, weather, aqi, fonts):
        cx = (x1 + x2) // 2
        pad = 15

        if not weather and not aqi:
            cy = (y1 + y2) // 2
            draw.text((cx - fonts["md"].getlength("Weather") // 2, cy - 15),
                       "Weather", fill=120, font=fonts["md"])
            msg = "Set location & coordinates"
            draw.text((cx - fonts["sm"].getlength(msg) // 2, cy + 12),
                       msg, fill=160, font=fonts["sm"])
            return

        y = y1 + pad

        if weather:
            # Weather icon on the left, temperature on the right
            icon_cx = x1 + 60
            icon_cy = y + 35
            self._draw_weather_icon(draw, icon_cx, icon_cy, weather.get("weather_code", 0), size=50)

            # Big temperature next to icon
            temp_str = f"{weather['temp_c']}°"
            temp_x = x1 + 110
            draw.text((temp_x, y + 2), temp_str, fill=0, font=fonts["xxl"])

            # Condition text below
            condition = weather["condition"]
            cw = fonts["md"].getlength(condition)
            draw.text((cx - cw // 2, y + 68), condition, fill=60, font=fonts["md"])

            # Details row: feels like + humidity
            details = []
            if weather.get("feels_like"):
                details.append(f"Feels {weather['feels_like']}°")
            if weather.get("humidity"):
                details.append(f"Humidity {weather['humidity']}%")
            detail_str = "  |  ".join(details)
            if detail_str:
                dw = fonts["xs"].getlength(detail_str)
                draw.text((cx - dw // 2, y + 96), detail_str, fill=120, font=fonts["xs"])

        # AQI bar at the bottom
        if aqi:
            bar_y = y2 - pad - 30
            bar_x = x1 + pad + 5
            bar_w = (x2 - x1) - pad * 2 - 10
            bar_h = 10

            # AQI scale bar (gradient from light to dark)
            segment_w = bar_w // 5
            fills = [220, 190, 150, 110, 70]
            for i, fill_val in enumerate(fills):
                sx = bar_x + i * segment_w
                sw = segment_w if i < 4 else bar_w - 4 * segment_w
                draw.rectangle([sx, bar_y, sx + sw, bar_y + bar_h], fill=fill_val)

            # Outer border
            draw.rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], outline=80, width=1)

            # Position marker on the bar
            max_aqi = 100
            aqi_val = min(aqi["value"], max_aqi)
            marker_x = bar_x + int(aqi_val / max_aqi * bar_w)
            # Triangle marker above bar
            draw.polygon([(marker_x - 5, bar_y - 2), (marker_x + 5, bar_y - 2),
                          (marker_x, bar_y + 3)], fill=0)

            # AQI label
            aqi_text = f"AQI {aqi['value']} - {aqi['label']}"
            aw = fonts["xs"].getlength(aqi_text)
            draw.text((cx - aw // 2, bar_y + bar_h + 4), aqi_text, fill=80, font=fonts["xs"])

    # ── Precipitation Radar (right side) ──────────────────────────────

    # Major cities for radar anchor points (name, lat, lon)
    MAJOR_CITIES = [
        # Europe
        ("London", 51.51, -0.13), ("Paris", 48.86, 2.35), ("Berlin", 52.52, 13.41),
        ("Madrid", 40.42, -3.70), ("Rome", 41.90, 12.50), ("Vienna", 48.21, 16.37),
        ("Prague", 50.08, 14.44), ("Warsaw", 52.23, 21.01), ("Budapest", 47.50, 19.04),
        ("Munich", 48.14, 11.58), ("Milan", 45.46, 9.19), ("Barcelona", 41.39, 2.17),
        ("Amsterdam", 52.37, 4.90), ("Brussels", 50.85, 4.35), ("Zurich", 47.38, 8.54),
        ("Copenhagen", 55.68, 12.57), ("Stockholm", 59.33, 18.07), ("Oslo", 59.91, 10.75),
        ("Helsinki", 60.17, 24.94), ("Dublin", 53.35, -6.26), ("Lisbon", 38.72, -9.14),
        ("Athens", 37.98, 23.73), ("Bucharest", 44.43, 26.10), ("Sofia", 42.70, 23.32),
        ("Belgrade", 44.79, 20.47), ("Zagreb", 45.81, 15.98), ("Bratislava", 48.15, 17.11),
        ("Ljubljana", 46.06, 14.51), ("Krakow", 50.06, 19.94), ("Hamburg", 53.55, 9.99),
        ("Frankfurt", 50.11, 8.68), ("Lyon", 45.76, 4.84), ("Marseille", 43.30, 5.37),
        ("Edinburgh", 55.95, -3.19), ("Manchester", 53.48, -2.24), ("Kyiv", 50.45, 30.52),
        ("Istanbul", 41.01, 28.98), ("Brno", 49.20, 16.61), ("Dresden", 51.05, 13.74),
        ("Nuremberg", 49.45, 11.08), ("Gdansk", 54.35, 18.65), ("Vilnius", 54.69, 25.28),
        ("Riga", 56.95, 24.11), ("Tallinn", 59.44, 24.75), ("Minsk", 53.90, 27.57),
        # Americas
        ("New York", 40.71, -74.01), ("Los Angeles", 34.05, -118.24),
        ("Chicago", 41.88, -87.63), ("Toronto", 43.65, -79.38), ("Mexico City", 19.43, -99.13),
        ("São Paulo", -23.55, -46.63), ("Buenos Aires", -34.60, -58.38),
        ("Washington", 38.91, -77.04), ("Miami", 25.76, -80.19), ("Boston", 42.36, -71.06),
        ("Montreal", 45.50, -73.57), ("Vancouver", 49.28, -123.12),
        ("San Francisco", 37.77, -122.42), ("Atlanta", 33.75, -84.39),
        ("Denver", 39.74, -104.99), ("Dallas", 32.78, -96.80),
        # Asia & Oceania
        ("Tokyo", 35.68, 139.69), ("Beijing", 39.90, 116.40), ("Shanghai", 31.23, 121.47),
        ("Seoul", 37.57, 126.98), ("Mumbai", 19.08, 72.88), ("Delhi", 28.61, 77.21),
        ("Singapore", 1.35, 103.82), ("Bangkok", 13.76, 100.50), ("Dubai", 25.20, 55.27),
        ("Sydney", -33.87, 151.21), ("Melbourne", -37.81, 144.96), ("Auckland", -36.85, 174.76),
        # Africa
        ("Cairo", 30.04, 31.24), ("Johannesburg", -26.20, 28.04),
        ("Lagos", 6.52, 3.38), ("Nairobi", -1.29, 36.82),
    ]

    def _latlon_to_tile(self, lat, lon, zoom):
        """Convert latitude/longitude to tile x/y at given zoom level."""
        lat_rad = math.radians(lat)
        n = 2 ** zoom
        x = int((lon + 180.0) / 360.0 * n)
        y = int((1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n)
        return x, y

    def _latlon_to_grid_pixel(self, lat, lon, zoom, center_tile_x, center_tile_y, tile_size=256):
        """Convert lat/lon to pixel position within the 3x3 tile grid."""
        lat_rad = math.radians(lat)
        n = 2 ** zoom
        # World pixel coordinates
        world_x = (lon + 180.0) / 360.0 * n * tile_size
        world_y = (1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n * tile_size
        # Grid origin is at tile (center-1, center-1)
        grid_origin_x = (center_tile_x - 1) * tile_size
        grid_origin_y = (center_tile_y - 1) * tile_size
        return world_x - grid_origin_x, world_y - grid_origin_y

    def _fetch_radar(self, latitude: str, longitude: str) -> tuple:
        """Returns (radar_image, radar_meta) where meta has tile info for city plotting."""
        if not latitude or not longitude:
            return None, {}
        try:
            import requests
            lat = float(latitude)
            lon = float(longitude)

            # Get available radar timestamps
            resp = requests.get("https://api.rainviewer.com/public/weather-maps.json", timeout=10)
            resp.raise_for_status()
            maps_data = resp.json()

            radar_frames = maps_data.get("radar", {}).get("past", [])
            if not radar_frames:
                return None, {}

            latest = radar_frames[-1]
            path = latest["path"]

            # Use zoom 6 for regional view, fetch a 3x3 grid of tiles for context
            zoom = 6
            center_x, center_y = self._latlon_to_tile(lat, lon, zoom)

            # Download 3x3 tile grid for wider area
            tile_size = 256
            grid = Image.new("RGBA", (tile_size * 3, tile_size * 3), (0, 0, 0, 0))

            for dy in range(-1, 2):
                for dx in range(-1, 2):
                    tx = center_x + dx
                    ty = center_y + dy
                    tile_url = f"https://tilecache.rainviewer.com{path}/{tile_size}/{zoom}/{tx}/{ty}/1/1_1.png"
                    try:
                        tile_resp = requests.get(tile_url, timeout=8)
                        if tile_resp.status_code == 200:
                            tile_img = Image.open(BytesIO(tile_resp.content)).convert("RGBA")
                            grid.paste(tile_img, ((dx + 1) * tile_size, (dy + 1) * tile_size))
                    except Exception:
                        pass

            meta = {
                "zoom": zoom, "center_x": center_x, "center_y": center_y,
                "tile_size": tile_size, "grid_size": tile_size * 3,
            }
            return grid, meta

        except Exception as e:
            logger.error(f"Radar fetch failed: {e}")
            return None, {}

    def _draw_radar(self, img, draw, x1, y1, x2, y2, radar_img, radar_meta, fonts):
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        quad_w = x2 - x1
        quad_h = y2 - y1

        if radar_img is None:
            draw.text((cx - fonts["md"].getlength("Radar") // 2, cy - 15),
                       "Radar", fill=120, font=fonts["md"])
            msg = "Set coordinates in settings"
            draw.text((cx - fonts["sm"].getlength(msg) // 2, cy + 12),
                       msg, fill=160, font=fonts["sm"])
            return

        # Resize radar to fit quadrant with padding
        pad = 8
        target_w = quad_w - pad * 2
        target_h = quad_h - pad * 2 - 18  # leave room for label

        radar_resized = radar_img.resize((target_w, target_h), Image.LANCZOS)

        # RainViewer tiles: RGBA where alpha=0 means no rain, higher alpha = precipitation
        # Convert to grayscale: no rain = white (240), light rain = light gray, heavy = dark
        r_ch, g_ch, b_ch, a_ch = radar_resized.split()

        radar_bg = Image.new("L", (target_w, target_h), 240)

        r_data = list(r_ch.getdata())
        g_data = list(g_ch.getdata())
        b_data = list(b_ch.getdata())
        a_data = list(a_ch.getdata())

        result = []
        for i in range(len(a_data)):
            if a_data[i] < 20:
                result.append(240)
            else:
                brightness = (r_data[i] + g_data[i] + b_data[i]) / 3
                alpha_factor = min(a_data[i] / 255, 1.0)
                shade = int(240 - (240 - brightness) * alpha_factor * 0.8)
                shade = max(40, min(220, shade))
                result.append(shade)

        radar_bg.putdata(result)

        # Paste onto main image
        img_x = x1 + pad
        img_y = y1 + pad + 14
        img.paste(radar_bg, (img_x, img_y))

        # Scale factors from 3x3 tile grid to rendered image
        grid_size = radar_meta.get("grid_size", 768)
        scale_x = target_w / grid_size
        scale_y = target_h / grid_size
        zoom = radar_meta.get("zoom", 6)
        ctx = radar_meta.get("center_x", 0)
        cty = radar_meta.get("center_y", 0)
        tile_size = radar_meta.get("tile_size", 256)

        # Draw city markers
        if radar_meta:
            label_rects = []  # track placed labels to avoid overlap
            for city_name, city_lat, city_lon in self.MAJOR_CITIES:
                gx, gy = self._latlon_to_grid_pixel(
                    city_lat, city_lon, zoom, ctx, cty, tile_size
                )
                # Check if within visible grid
                if gx < 0 or gx >= grid_size or gy < 0 or gy >= grid_size:
                    continue

                # Convert to screen coordinates
                sx = int(img_x + gx * scale_x)
                sy = int(img_y + gy * scale_y)

                # Skip if too close to edges
                if sx < img_x + 5 or sx > img_x + target_w - 5:
                    continue
                if sy < img_y + 5 or sy > img_y + target_h - 5:
                    continue

                # Draw small dot
                r = 2
                draw.ellipse([sx - r, sy - r, sx + r, sy + r], fill=60)

                # Draw label (offset to right of dot)
                lbl = city_name
                lbl_w = fonts["xs"].getlength(lbl)
                lbl_x = sx + 5
                lbl_y = sy - 6

                # If label would go off-screen, place left of dot
                if lbl_x + lbl_w > img_x + target_w - 2:
                    lbl_x = sx - lbl_w - 5

                # Check overlap with existing labels
                lbl_rect = (lbl_x, lbl_y, lbl_x + lbl_w, lbl_y + 12)
                overlap = False
                for existing in label_rects:
                    if (lbl_rect[0] < existing[2] + 4 and lbl_rect[2] > existing[0] - 4 and
                            lbl_rect[1] < existing[3] + 2 and lbl_rect[3] > existing[1] - 2):
                        overlap = True
                        break
                if overlap:
                    continue

                label_rects.append(lbl_rect)
                draw.text((lbl_x, lbl_y), lbl, fill=40, font=fonts["xs"])

        # Draw crosshair at center for user's location
        marker_x = x1 + pad + target_w // 2
        marker_y = y1 + pad + 14 + target_h // 2
        cr = 4
        draw.ellipse([marker_x - cr, marker_y - cr, marker_x + cr, marker_y + cr],
                      outline=0, width=2)
        draw.line([(marker_x - 8, marker_y), (marker_x + 8, marker_y)], fill=0, width=1)
        draw.line([(marker_x, marker_y - 8), (marker_x, marker_y + 8)], fill=0, width=1)

        # Label
        label = "Precipitation Radar"
        lw = fonts["xs"].getlength(label)
        draw.text((cx - lw // 2, y1 + 2), label, fill=100, font=fonts["xs"])

    # ── Shared helpers ───────────────────────────────────────────────

    def _wrap_text(self, text, font, max_width):
        words = text.split()
        lines = []
        current_line = ""
        for word in words:
            test = f"{current_line} {word}".strip()
            if font.getlength(test) <= max_width:
                current_line = test
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)
        return lines or [""]
