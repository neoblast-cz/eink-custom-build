import math
import logging
from io import BytesIO
from datetime import datetime
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
    DESCRIPTION = "Affirmations, traffic, weather/AQI, and precipitation radar"

    def render(self, width: int, height: int, settings: dict) -> Image.Image:
        img = Image.new("L", (width, height), 255)
        draw = ImageDraw.Draw(img)
        fonts = self._load_fonts()

        mid_x = width // 2
        mid_y = height // 2

        # Divider lines
        draw.line([(mid_x, 10), (mid_x, height - 10)], fill=180, width=1)
        draw.line([(10, mid_y), (width - 10, mid_y)], fill=180, width=1)

        # Top-left: Daily affirmation
        affirmation = self._fetch_affirmation()
        font_size_name = settings.get("message_font", "medium")
        self._draw_message(draw, 0, 0, mid_x, mid_y, affirmation, font_size_name, fonts)

        # Top-right: Traffic commute
        traffic = self._fetch_traffic(settings)
        self._draw_traffic(draw, mid_x, 0, width, mid_y, traffic, fonts)

        # Bottom-left: Weather + AQI
        weather = self._fetch_weather(settings.get("weather_location", ""))
        aqi = self._fetch_aqi(settings.get("latitude", ""), settings.get("longitude", ""))
        self._draw_weather_aqi(draw, 0, mid_y, mid_x, height, weather, aqi, fonts)

        # Bottom-right: Precipitation radar
        radar_img = self._fetch_radar(settings.get("latitude", ""), settings.get("longitude", ""))
        self._draw_radar(img, draw, mid_x, mid_y, width, height, radar_img, fonts)

        return img

    def default_settings(self) -> dict:
        return {
            "weather_location": "",
            "latitude": "",
            "longitude": "",
            "message_font": "medium",
            "google_maps_api_key": "",
            "home_address": "",
            "office_address": "",
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
        sizes = [("xl", 40), ("lg", 30), ("md", 22), ("sm", 16), ("xs", 13)]
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

    # ── Traffic (top-right) ──────────────────────────────────────────

    def _fetch_traffic(self, settings: dict) -> dict:
        api_key = settings.get("google_maps_api_key", "")
        home = settings.get("home_address", "")
        office = settings.get("office_address", "")

        if not api_key or not home or not office:
            return {}

        hour = datetime.now().hour
        if hour < 14:
            origin, destination = home, office
            label = "To Office"
        else:
            origin, destination = office, home
            label = "To Home"

        try:
            import requests
            resp = requests.get(
                "https://maps.googleapis.com/maps/api/directions/json",
                params={
                    "origin": origin,
                    "destination": destination,
                    "departure_time": "now",
                    "key": api_key,
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("status") != "OK" or not data.get("routes"):
                logger.error(f"Directions API error: {data.get('status')}")
                return {"label": label, "error": data.get("status", "No route")}

            leg = data["routes"][0]["legs"][0]
            duration_traffic = leg.get("duration_in_traffic", leg.get("duration", {}))
            return {
                "label": label,
                "duration": duration_traffic.get("text", "?"),
                "distance": leg.get("distance", {}).get("text", ""),
                "summary": data["routes"][0].get("summary", ""),
            }
        except Exception as e:
            logger.error(f"Traffic fetch failed: {e}")
            return {"label": label, "error": str(e)}

    def _draw_traffic(self, draw, x1, y1, x2, y2, traffic, fonts):
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2

        if not traffic:
            draw.text((cx - fonts["md"].getlength("Traffic") // 2, cy - 15),
                       "Traffic", fill=120, font=fonts["md"])
            msg = "Set API key & addresses"
            draw.text((cx - fonts["sm"].getlength(msg) // 2, cy + 12),
                       msg, fill=160, font=fonts["sm"])
            return

        label = traffic.get("label", "Commute")
        lw = fonts["md"].getlength(label)
        draw.text((cx - lw // 2, cy - 55), label, fill=80, font=fonts["md"])

        if "error" in traffic:
            err = traffic["error"][:30]
            ew = fonts["sm"].getlength(err)
            draw.text((cx - ew // 2, cy - 10), err, fill=100, font=fonts["sm"])
            return

        # Duration (large)
        duration = traffic.get("duration", "?")
        dw = fonts["xl"].getlength(duration)
        draw.text((cx - dw // 2, cy - 25), duration, fill=0, font=fonts["xl"])

        # Distance + route
        details = traffic.get("distance", "")
        if traffic.get("summary"):
            details += f" via {traffic['summary']}"
        if details:
            # Truncate if too long
            max_w = x2 - x1 - 30
            while fonts["sm"].getlength(details) > max_w and len(details) > 3:
                details = details[:-4] + "..."
            dtw = fonts["sm"].getlength(details)
            draw.text((cx - dtw // 2, cy + 25), details, fill=120, font=fonts["sm"])

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
                "condition": current["weatherDesc"][0]["value"],
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

    def _draw_weather_aqi(self, draw, x1, y1, x2, y2, weather, aqi, fonts):
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2

        if not weather and not aqi:
            draw.text((cx - fonts["md"].getlength("Weather") // 2, cy - 15),
                       "Weather", fill=120, font=fonts["md"])
            msg = "Set location & coordinates"
            draw.text((cx - fonts["sm"].getlength(msg) // 2, cy + 12),
                       msg, fill=160, font=fonts["sm"])
            return

        # Split: temperature on the left third, AQI circle on the right third
        section_w = x2 - x1
        temp_cx = x1 + section_w // 3
        aqi_cx = x1 + (section_w * 2) // 3

        # Temperature
        if weather:
            temp_str = f"{weather['temp_c']}°C"
            tw = fonts["xl"].getlength(temp_str)
            draw.text((temp_cx - tw // 2, cy - 35), temp_str, fill=0, font=fonts["xl"])

            condition = weather["condition"]
            cw = fonts["sm"].getlength(condition)
            draw.text((temp_cx - cw // 2, cy + 15), condition, fill=80, font=fonts["sm"])

            loc = weather["location"].title()
            lw = fonts["xs"].getlength(loc)
            draw.text((temp_cx - lw // 2, cy + 38), loc, fill=140, font=fonts["xs"])

        # AQI circle
        if aqi:
            r = 40
            shade = aqi["shade"]
            # Draw filled circle
            draw.ellipse(
                [aqi_cx - r, cy - r - 5, aqi_cx + r, cy + r - 5],
                fill=shade, outline=0, width=2,
            )
            # AQI value in center
            val_str = str(aqi["value"])
            text_fill = 0 if shade > 120 else 255
            vw = fonts["lg"].getlength(val_str)
            draw.text((aqi_cx - vw // 2, cy - 22), val_str, fill=text_fill, font=fonts["lg"])

            # Label below circle
            label = aqi["label"]
            llw = fonts["sm"].getlength(label)
            draw.text((aqi_cx - llw // 2, cy + r + 2), label, fill=80, font=fonts["sm"])

            # "AQI" tiny label above circle
            aq_label = "AQI"
            aw = fonts["xs"].getlength(aq_label)
            draw.text((aqi_cx - aw // 2, cy - r - 20), aq_label, fill=120, font=fonts["xs"])

    # ── Precipitation Radar (bottom-right) ───────────────────────────

    def _latlon_to_tile(self, lat, lon, zoom):
        """Convert latitude/longitude to tile x/y at given zoom level."""
        lat_rad = math.radians(lat)
        n = 2 ** zoom
        x = int((lon + 180.0) / 360.0 * n)
        y = int((1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n)
        return x, y

    def _fetch_radar(self, latitude: str, longitude: str) -> Image.Image | None:
        if not latitude or not longitude:
            return None
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
                return None

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

            return grid

        except Exception as e:
            logger.error(f"Radar fetch failed: {e}")
            return None

    def _draw_radar(self, img, draw, x1, y1, x2, y2, radar_img, fonts):
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
        # Colors indicate intensity (green=light, yellow=moderate, red=heavy)
        # Convert to grayscale: no rain = white (240), light rain = light gray, heavy = dark
        r_ch, g_ch, b_ch, a_ch = radar_resized.split()

        # Create grayscale background
        radar_bg = Image.new("L", (target_w, target_h), 240)

        # For each pixel: if alpha > threshold, darken based on intensity
        # Use the RGB brightness + alpha to determine rain intensity
        r_data = list(r_ch.getdata())
        g_data = list(g_ch.getdata())
        b_data = list(b_ch.getdata())
        a_data = list(a_ch.getdata())

        result = []
        for i in range(len(a_data)):
            if a_data[i] < 20:
                result.append(240)  # no rain: light background
            else:
                # Brightness of the rain color (lower = more intense rain)
                brightness = (r_data[i] + g_data[i] + b_data[i]) / 3
                # Map: green (bright, ~170) = light rain -> gray 190
                #       red (mid, ~130) = moderate -> gray 140
                #       dark red/purple (dark, ~80) = heavy -> gray 60
                alpha_factor = min(a_data[i] / 255, 1.0)
                shade = int(240 - (240 - brightness) * alpha_factor * 0.8)
                shade = max(40, min(220, shade))
                result.append(shade)

        radar_bg.putdata(result)

        # Paste onto main image
        img.paste(radar_bg, (x1 + pad, y1 + pad + 14))

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
