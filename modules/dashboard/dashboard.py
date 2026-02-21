import logging
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


class DashboardModule(BaseModule):
    NAME = "dashboard"
    DISPLAY_NAME = "Dashboard"
    DESCRIPTION = "Shows time, Duolingo streak, weather, and a daily affirmation"

    def render(self, width: int, height: int, settings: dict) -> Image.Image:
        img = Image.new("L", (width, height), 255)
        draw = ImageDraw.Draw(img)
        fonts = self._load_fonts()

        mid_x = width // 2
        mid_y = height // 2

        # Divider lines
        draw.line([(mid_x, 10), (mid_x, height - 10)], fill=180, width=1)
        draw.line([(10, mid_y), (width - 10, mid_y)], fill=180, width=1)

        # Top-left: Time
        self._draw_time(draw, 0, 0, mid_x, mid_y, fonts)

        # Top-right: Duolingo streak
        streak = self._fetch_duolingo_streak(settings.get("duolingo_username", ""))
        self._draw_duolingo(draw, mid_x, 0, width, mid_y, streak, fonts)

        # Bottom-left: Daily affirmation
        affirmation = self._fetch_affirmation()
        font_size_name = settings.get("message_font", "medium")
        self._draw_message(draw, 0, mid_y, mid_x, height, affirmation, font_size_name, fonts)

        # Bottom-right: Weather
        weather = self._fetch_weather(settings.get("weather_location", ""))
        self._draw_weather(draw, mid_x, mid_y, width, height, weather, fonts)

        return img

    def default_settings(self) -> dict:
        return {
            "duolingo_username": "neoblast",
            "weather_location": "",
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
        sizes = [("time", 64), ("xl", 40), ("lg", 30), ("md", 22), ("sm", 16), ("xs", 13)]
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

    def _draw_time(self, draw, x1, y1, x2, y2, fonts):
        now = datetime.now()
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2

        # Time
        time_str = now.strftime("%H:%M")
        tw = fonts["time"].getlength(time_str)
        draw.text((cx - tw // 2, cy - 55), time_str, fill=0, font=fonts["time"])

        # Day of week
        day_str = now.strftime("%A")
        dw = fonts["md"].getlength(day_str)
        draw.text((cx - dw // 2, cy + 15), day_str, fill=80, font=fonts["md"])

        # Date
        date_str = now.strftime("%d %B %Y")
        dtw = fonts["sm"].getlength(date_str)
        draw.text((cx - dtw // 2, cy + 42), date_str, fill=120, font=fonts["sm"])

    def _fetch_duolingo_streak(self, username: str) -> int:
        if not username:
            return -1
        try:
            import requests
            url = "https://www.duolingo.com/2017-06-30/users"
            resp = requests.get(url, params={
                "username": username,
                "fields": "streak",
            }, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            users = data.get("users", [])
            if users:
                return users[0].get("streak", 0)
            return 0
        except Exception as e:
            logger.error(f"Duolingo fetch failed: {e}")
            return -1

    def _draw_duolingo(self, draw, x1, y1, x2, y2, streak, fonts):
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2

        if streak < 0:
            draw.text((cx - fonts["md"].getlength("Duolingo") // 2, cy - 15),
                       "Duolingo", fill=120, font=fonts["md"])
            msg = "Set username in settings"
            draw.text((cx - fonts["sm"].getlength(msg) // 2, cy + 12),
                       msg, fill=160, font=fonts["sm"])
            return

        # Streak number
        streak_str = str(streak)
        sw = fonts["xl"].getlength(streak_str)
        draw.text((cx - sw // 2, cy - 45), streak_str, fill=0, font=fonts["xl"])

        # "days" label
        days_label = "day streak" if streak == 1 else "days streak"
        dlw = fonts["md"].getlength(days_label)
        draw.text((cx - dlw // 2, cy + 5), days_label, fill=80, font=fonts["md"])

        # "Duolingo" subtitle
        label = "Duolingo"
        lw = fonts["sm"].getlength(label)
        draw.text((cx - lw // 2, cy + 35), label, fill=140, font=fonts["sm"])

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

    def _fetch_affirmation(self) -> str:
        try:
            import requests
            resp = requests.get("https://www.affirmations.dev", timeout=10)
            resp.raise_for_status()
            return resp.json().get("affirmation", "You are doing great!")
        except Exception as e:
            logger.error(f"Affirmation fetch failed: {e}")
            return "You are doing great!"

    def _draw_weather(self, draw, x1, y1, x2, y2, weather, fonts):
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2

        if not weather:
            draw.text((cx - fonts["md"].getlength("Weather") // 2, cy - 15),
                       "Weather", fill=120, font=fonts["md"])
            msg = "Set location in settings"
            draw.text((cx - fonts["sm"].getlength(msg) // 2, cy + 12),
                       msg, fill=160, font=fonts["sm"])
            return

        # Temperature
        temp_str = f"{weather['temp_c']}°C"
        tw = fonts["xl"].getlength(temp_str)
        draw.text((cx - tw // 2, cy - 45), temp_str, fill=0, font=fonts["xl"])

        # Condition
        condition = weather["condition"]
        cw = fonts["md"].getlength(condition)
        draw.text((cx - cw // 2, cy + 5), condition, fill=80, font=fonts["md"])

        # Location
        loc = weather["location"].title()
        lw = fonts["sm"].getlength(loc)
        draw.text((cx - lw // 2, cy + 35), loc, fill=140, font=fonts["sm"])

    def _draw_message(self, draw, x1, y1, x2, y2, message, font_size_name, fonts):
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        max_w = x2 - x1 - 40  # padding

        # Get the right font size
        size = MESSAGE_FONT_SIZES.get(font_size_name, 22)
        font_key = {16: "sm", 22: "md", 30: "lg", 40: "xl"}.get(size, "md")
        font = fonts[font_key]

        # Word-wrap the message
        lines = self._wrap_text(message, font, max_w)

        # Center vertically
        line_h = size + 6
        total_h = len(lines) * line_h
        start_y = cy - total_h // 2

        for i, line in enumerate(lines):
            lw = font.getlength(line)
            draw.text((cx - lw // 2, start_y + i * line_h), line, fill=0, font=font)

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
