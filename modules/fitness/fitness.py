import json
import math
import logging
import time
import base64
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont
from modules.base import BaseModule

logger = logging.getLogger(__name__)

TOKEN_PATH = Path(__file__).parent.parent.parent / "fitbit_token.json"
FITBIT_API = "https://api.fitbit.com"


class FitnessModule(BaseModule):
    NAME = "fitness"
    DISPLAY_NAME = "Fitness"
    DESCRIPTION = "Fitbit steps, heart rate, and weight"

    def render(self, width: int, height: int, settings: dict) -> Image.Image:
        token = self._refresh_if_needed(settings)
        if not token:
            return self._draw_not_authorized(width, height)

        steps = self._fetch_steps(token)
        heart = self._fetch_heart(token)
        weight = self._fetch_weight(token)
        step_goal = int(settings.get("step_goal", 10000))
        weight_unit = settings.get("weight_unit", "kg")

        return self._draw(width, height, steps, heart, weight, step_goal, weight_unit)

    def default_settings(self) -> dict:
        return {"weight_unit": "kg", "step_goal": "10000"}

    # ── Token management ───────────────────────────────────────────

    def _load_token(self) -> dict | None:
        if not TOKEN_PATH.exists():
            return None
        try:
            return json.loads(TOKEN_PATH.read_text())
        except Exception:
            return None

    def _save_token(self, token_data: dict):
        TOKEN_PATH.write_text(json.dumps(token_data, indent=2))

    def _refresh_if_needed(self, settings: dict) -> str | None:
        token_data = self._load_token()
        if not token_data:
            return None

        access_token = token_data.get("access_token", "")
        expires_at = token_data.get("expires_at", 0)

        if time.time() < expires_at - 300:
            return access_token

        refresh_token = token_data.get("refresh_token", "")
        if not refresh_token:
            return None

        client_id = settings.get("_fitbit_client_id", "")
        client_secret = settings.get("_fitbit_client_secret", "")
        if not client_id or not client_secret:
            logger.warning("Fitbit credentials not injected, cannot refresh token")
            return access_token if time.time() < expires_at else None

        try:
            auth_header = base64.b64encode(
                f"{client_id}:{client_secret}".encode()
            ).decode()
            data = urllib.parse.urlencode({
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            }).encode()
            req = urllib.request.Request(
                f"{FITBIT_API}/oauth2/token",
                data=data,
                headers={
                    "Authorization": f"Basic {auth_header}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                new_token = json.loads(resp.read())

            new_token["expires_at"] = time.time() + new_token.get("expires_in", 28800)
            self._save_token(new_token)
            logger.info("Fitbit token refreshed successfully")
            return new_token["access_token"]
        except Exception as e:
            logger.error(f"Fitbit token refresh failed: {e}")
            return access_token if time.time() < expires_at else None

    # ── API helpers ────────────────────────────────────────────────

    def _api_get(self, url: str, access_token: str) -> dict:
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {access_token}",
            "Accept-Language": "en_US",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())

    def _fetch_steps(self, token: str) -> dict:
        try:
            data = self._api_get(
                f"{FITBIT_API}/1/user/-/activities/date/today.json", token
            )
            logger.info(f"Fitbit activities keys: {list(data.keys())}")
            summary = data.get("summary", {})
            logger.info(f"Fitbit summary: steps={summary.get('steps')}, calories={summary.get('caloriesOut')}")
            return {
                "steps": summary.get("steps", 0),
                "calories": summary.get("caloriesOut", 0),
                "distance": summary.get("distances", [{}])[0].get("distance", 0),
            }
        except Exception as e:
            logger.error(f"Fitbit steps fetch failed: {e}")
            return {}

    def _fetch_heart(self, token: str) -> dict:
        try:
            data = self._api_get(
                f"{FITBIT_API}/1/user/-/activities/heart/date/today/1d.json", token
            )
            logger.info(f"Fitbit heart keys: {list(data.keys())}")
            heart_data = data.get("activities-heart", [{}])[0].get("value", {})
            resting = heart_data.get("restingHeartRate", 0)
            logger.info(f"Fitbit heart: resting={resting}, zones={heart_data.get('heartRateZones', [])}")
            zones = {}
            total_active = 0
            for zone in heart_data.get("heartRateZones", []):
                name = zone.get("name", "")
                minutes = zone.get("minutes", 0)
                zones[name] = minutes
                if name in ("Fat Burn", "Cardio", "Peak"):
                    total_active += minutes
            return {
                "resting": resting,
                "zones": zones,
                "active_minutes": total_active,
            }
        except Exception as e:
            logger.error(f"Fitbit heart rate fetch failed: {e}")
            return {}

    def _fetch_weight(self, token: str) -> dict:
        try:
            data = self._api_get(
                f"{FITBIT_API}/1/user/-/body/log/weight/date/today/1m.json", token
            )
            logger.info(f"Fitbit weight raw: {data}")
            entries = data.get("weight", [])
            points = [
                {"date": e.get("date", ""), "weight": e.get("weight", 0)}
                for e in entries
            ]
            latest = points[-1]["weight"] if points else 0
            return {"latest": latest, "points": points}
        except Exception as e:
            logger.error(f"Fitbit weight fetch failed: {e}")
            return {}

    # ── Font loading ───────────────────────────────────────────────

    def _load_fonts(self):
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "C:/Windows/Fonts/segoeuib.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
        ]
        fonts = {}
        for size_name, size in [("xxl", 48), ("xl", 36), ("lg", 26), ("md", 18),
                                 ("sm", 14), ("xs", 11)]:
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

    # ── Drawing ────────────────────────────────────────────────────

    def _draw_not_authorized(self, width: int, height: int) -> Image.Image:
        img = Image.new("L", (width, height), 255)
        draw = ImageDraw.Draw(img)
        fonts = self._load_fonts()
        cx, cy = width // 2, height // 2
        msg = "Fitness"
        mw = fonts["lg"].getlength(msg)
        draw.text((cx - mw // 2, cy - 30), msg, fill=0, font=fonts["lg"])
        hint = "Authorize Fitbit in module settings"
        hw = fonts["sm"].getlength(hint)
        draw.text((cx - hw // 2, cy + 10), hint, fill=120, font=fonts["sm"])
        return img

    def _draw(self, width, height, steps, heart, weight, step_goal, weight_unit):
        img = Image.new("L", (width, height), 255)
        draw = ImageDraw.Draw(img)
        fonts = self._load_fonts()
        margin = 15

        # Title bar
        draw.text((margin, margin), "Fitness", fill=0, font=fonts["lg"])
        now = datetime.now()
        date_str = now.strftime("%a, %b %d")
        dw = fonts["sm"].getlength(date_str)
        draw.text((width - margin - dw, margin + 5), date_str, fill=100, font=fonts["sm"])
        title_y = margin + 36
        draw.line([(margin, title_y), (width - margin, title_y)], fill=180, width=1)

        # Three columns
        col_w = (width - margin * 2) // 3
        top_y = title_y + 12
        col_h = height - top_y - margin

        # Vertical dividers
        x1 = margin + col_w
        x2 = margin + col_w * 2
        draw.line([(x1, top_y + 5), (x1, height - margin)], fill=180, width=1)
        draw.line([(x2, top_y + 5), (x2, height - margin)], fill=180, width=1)

        self._draw_steps(draw, margin, top_y, col_w, col_h, steps, step_goal, fonts)
        self._draw_heart(draw, x1, top_y, col_w, col_h, heart, fonts)
        self._draw_weight(draw, x2, top_y, col_w, col_h, weight, weight_unit, fonts)

        return img

    def _draw_steps(self, draw, x, y, w, h, steps_data, goal, fonts):
        pad = 15
        cx = x + w // 2
        y += pad

        # Sub-header
        header = "Steps"
        hw = fonts["md"].getlength(header)
        draw.text((cx - hw // 2, y), header, fill=80, font=fonts["md"])
        y += 30

        count = steps_data.get("steps", 0)

        # Walking icon (simple stick figure)
        icon_cx = cx
        icon_cy = y + 35
        # Head
        draw.ellipse([icon_cx - 6, icon_cy - 28, icon_cx + 6, icon_cy - 16], outline=0, width=2)
        # Body
        draw.line([(icon_cx, icon_cy - 16), (icon_cx, icon_cy + 5)], fill=0, width=2)
        # Arms
        draw.line([(icon_cx, icon_cy - 10), (icon_cx - 12, icon_cy - 2)], fill=0, width=2)
        draw.line([(icon_cx, icon_cy - 10), (icon_cx + 12, icon_cy + 2)], fill=0, width=2)
        # Legs (walking pose)
        draw.line([(icon_cx, icon_cy + 5), (icon_cx - 10, icon_cy + 22)], fill=0, width=2)
        draw.line([(icon_cx, icon_cy + 5), (icon_cx + 10, icon_cy + 22)], fill=0, width=2)
        y += 75

        # Step count
        count_str = f"{count:,}"
        cw = fonts["xxl"].getlength(count_str)
        draw.text((cx - cw // 2, y), count_str, fill=0, font=fonts["xxl"])
        y += 55

        label = "steps today"
        lw = fonts["sm"].getlength(label)
        draw.text((cx - lw // 2, y), label, fill=100, font=fonts["sm"])
        y += 30

        # Progress bar
        bar_x = x + pad + 5
        bar_w = w - pad * 2 - 10
        bar_h = 12
        progress = min(count / goal, 1.0) if goal > 0 else 0

        # Background
        draw.rectangle([bar_x, y, bar_x + bar_w, y + bar_h], fill=230, outline=180)
        # Fill
        if progress > 0:
            fill_w = int(bar_w * progress)
            draw.rectangle([bar_x, y, bar_x + fill_w, y + bar_h], fill=80)
        y += bar_h + 8

        # Goal label
        pct = int(progress * 100)
        goal_str = f"{pct}% of {goal:,}"
        gw = fonts["xs"].getlength(goal_str)
        draw.text((cx - gw // 2, y), goal_str, fill=120, font=fonts["xs"])

    def _draw_heart(self, draw, x, y, w, h, heart_data, fonts):
        pad = 15
        cx = x + w // 2
        y += pad

        header = "Heart"
        hw = fonts["md"].getlength(header)
        draw.text((cx - hw // 2, y), header, fill=80, font=fonts["md"])
        y += 30

        # Heart icon
        hx, hy = cx, y + 20
        # Two arcs forming a heart shape
        draw.ellipse([hx - 14, hy - 10, hx, hy + 2], outline=0, width=2)
        draw.ellipse([hx, hy - 10, hx + 14, hy + 2], outline=0, width=2)
        draw.polygon([(hx - 14, hy - 2), (hx, hy + 14), (hx + 14, hy - 2)], outline=0)
        y += 45

        resting = heart_data.get("resting", 0)
        if resting:
            resting_str = f"{resting} bpm"
            rw = fonts["xl"].getlength(resting_str)
            draw.text((cx - rw // 2, y), resting_str, fill=0, font=fonts["xl"])
            y += 42

            label = "resting"
            lw = fonts["sm"].getlength(label)
            draw.text((cx - lw // 2, y), label, fill=100, font=fonts["sm"])
            y += 30
        else:
            msg = "No HR data"
            mw = fonts["md"].getlength(msg)
            draw.text((cx - mw // 2, y), msg, fill=140, font=fonts["md"])
            y += 35

        # Zone breakdown
        zones = heart_data.get("zones", {})
        active = heart_data.get("active_minutes", 0)

        if active > 0:
            draw.line([(x + pad, y), (x + w - pad, y)], fill=200, width=1)
            y += 10

            active_str = f"Active: {active} min"
            aw = fonts["sm"].getlength(active_str)
            draw.text((cx - aw // 2, y), active_str, fill=0, font=fonts["sm"])
            y += 22

            for zone_name in ["Fat Burn", "Cardio", "Peak"]:
                minutes = zones.get(zone_name, 0)
                if minutes > 0:
                    zone_str = f"{zone_name}: {minutes}m"
                    zw = fonts["xs"].getlength(zone_str)
                    draw.text((cx - zw // 2, y), zone_str, fill=120, font=fonts["xs"])
                    y += 18

    def _draw_weight(self, draw, x, y, w, h, weight_data, unit, fonts):
        pad = 15
        cx = x + w // 2
        y += pad

        header = "Weight"
        hw = fonts["md"].getlength(header)
        draw.text((cx - hw // 2, y), header, fill=80, font=fonts["md"])
        y += 35

        latest = weight_data.get("latest", 0)
        points = weight_data.get("points", [])

        if latest > 0:
            if unit == "lbs":
                display_val = latest * 2.20462
                unit_str = "lbs"
            else:
                display_val = latest
                unit_str = "kg"

            val_str = f"{display_val:.1f}"
            vw = fonts["xxl"].getlength(val_str)
            uw = fonts["md"].getlength(f" {unit_str}")
            total_w = vw + uw
            start_x = cx - total_w // 2
            draw.text((start_x, y), val_str, fill=0, font=fonts["xxl"])
            draw.text((start_x + vw, y + 14), f" {unit_str}", fill=100, font=fonts["md"])
            y += 65
        else:
            msg = "No weight data"
            mw = fonts["md"].getlength(msg)
            draw.text((cx - mw // 2, y + 20), msg, fill=140, font=fonts["md"])
            y += 60

        # Mini chart
        if len(points) >= 2:
            chart_x = x + pad
            chart_w = w - pad * 2
            chart_h = h - (y - (x + pad)) - 30
            chart_h = min(chart_h, 200)
            self._draw_mini_chart(draw, chart_x, y, chart_w, chart_h, points, unit, fonts)

    def _draw_mini_chart(self, draw, x, y, w, h, points, unit, fonts):
        weights = [p["weight"] for p in points]
        if unit == "lbs":
            weights = [wt * 2.20462 for wt in weights]

        min_w = min(weights)
        max_w = max(weights)
        range_w = max_w - min_w if max_w != min_w else 1.0

        # Add padding to range
        min_w -= range_w * 0.1
        max_w += range_w * 0.1
        range_w = max_w - min_w

        pad = 8
        chart_left = x + 35  # space for y-axis labels
        chart_right = x + w - pad
        chart_top = y + pad
        chart_bottom = y + h - 18  # space for x-axis hint
        chart_w = chart_right - chart_left
        chart_h = chart_bottom - chart_top

        # Chart border
        draw.line([(chart_left, chart_top), (chart_left, chart_bottom)], fill=180, width=1)
        draw.line([(chart_left, chart_bottom), (chart_right, chart_bottom)], fill=180, width=1)

        # Y-axis labels
        draw.text((x, chart_top - 2), f"{max_w:.0f}", fill=140, font=fonts["xs"])
        draw.text((x, chart_bottom - 10), f"{min_w:.0f}", fill=140, font=fonts["xs"])

        # Plot points
        coords = []
        n = len(weights)
        for i, wt in enumerate(weights):
            px = chart_left + (i * chart_w // (n - 1) if n > 1 else chart_w // 2)
            py = chart_bottom - int((wt - min_w) / range_w * chart_h)
            coords.append((px, py))

        # Draw connecting lines
        for i in range(len(coords) - 1):
            draw.line([coords[i], coords[i + 1]], fill=60, width=2)

        # Latest point marker
        last = coords[-1]
        draw.ellipse([last[0] - 4, last[1] - 4, last[0] + 4, last[1] + 4], fill=0)

        # X-axis hint
        hint = f"Last {len(points)} days"
        hw = fonts["xs"].getlength(hint)
        draw.text(((chart_left + chart_right) // 2 - hw // 2, chart_bottom + 3),
                  hint, fill=160, font=fonts["xs"])
