import calendar
import logging
from datetime import datetime, timedelta, date
from PIL import Image, ImageDraw, ImageFont
from modules.base import BaseModule

logger = logging.getLogger(__name__)


class CalendarModule(BaseModule):
    NAME = "calendar"
    DISPLAY_NAME = "Calendar"
    DESCRIPTION = "Shows a monthly calendar and upcoming events from an ICS feed"

    def render(self, width: int, height: int, settings: dict) -> Image.Image:
        events = self._fetch_events(settings)
        return self._draw(width, height, events, settings)

    def default_settings(self) -> dict:
        return {
            "ics_url": "",
            "days_ahead": 7,
            "max_events": 8,
        }

    def _fetch_events(self, settings: dict) -> list:
        ics_url = settings.get("ics_url", "")
        if not ics_url:
            return []

        try:
            import requests
            from icalendar import Calendar
            from dateutil.tz import tzlocal

            response = requests.get(ics_url, timeout=15)
            response.raise_for_status()
            cal = Calendar.from_ical(response.text)

            now = datetime.now(tzlocal())
            end = now + timedelta(days=int(settings.get("days_ahead", 7)))
            max_events = int(settings.get("max_events", 8))

            events = []
            for component in cal.walk():
                if component.name != "VEVENT":
                    continue

                dtstart = component.get("dtstart")
                if dtstart is None:
                    continue
                dt = dtstart.dt

                if isinstance(dt, datetime):
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=tzlocal())
                    all_day = False
                else:
                    dt = datetime.combine(dt, datetime.min.time(), tzinfo=tzlocal())
                    all_day = True

                if dt < end and dt >= now - timedelta(hours=1):
                    events.append({
                        "summary": str(component.get("summary", "Untitled")),
                        "start": dt,
                        "all_day": all_day,
                    })

            events.sort(key=lambda e: e["start"])
            return events[:max_events]

        except ImportError:
            logger.error("Install icalendar: pip install icalendar requests python-dateutil")
            return []
        except Exception as e:
            logger.error(f"Calendar fetch failed: {e}")
            return []

    def _get_event_day_counts(self, events: list) -> dict:
        """Get dict of day number -> event count for the current month."""
        today = datetime.now()
        counts = {}
        for event in events:
            dt = event["start"]
            if dt.year == today.year and dt.month == today.month:
                counts[dt.day] = counts.get(dt.day, 0) + 1
        return counts

    def _load_fonts(self):
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
            "C:/Windows/Fonts/segoeuib.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]
        fonts = {}
        for size_name, size in [("lg", 26), ("md", 17), ("sm", 13), ("xs", 11)]:
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

    def _draw(self, width: int, height: int, events: list, settings: dict) -> Image.Image:
        img = Image.new("L", (width, height), 255)
        draw = ImageDraw.Draw(img)
        fonts = self._load_fonts()

        event_day_counts = self._get_event_day_counts(events)

        # Layout: left panel uses full height for month grid, right panel for events
        left_w = 300
        self._draw_month_grid(draw, 15, 15, left_w - 30, height - 30, event_day_counts, fonts)

        # Vertical divider
        draw.line([(left_w, 10), (left_w, height - 10)], fill=180, width=1)

        # Right panel: events list
        self._draw_events(draw, left_w + 20, 15, width - 15, height - 15, events, fonts)

        return img

    def _draw_month_grid(self, draw, x, y, w, h, event_day_counts, fonts):
        today = datetime.now()

        # Month/year header
        header = today.strftime("%B %Y")
        draw.text((x, y), header, fill=0, font=fonts["lg"])
        y += 42

        # Day-of-week headers
        days = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
        cell_w = w // 7
        for i, d in enumerate(days):
            cx = x + i * cell_w
            draw.text((cx + (cell_w - fonts["sm"].getlength(d)) // 2, y), d, fill=100, font=fonts["sm"])
        y += 24

        # Separator
        draw.line([(x, y), (x + w, y)], fill=200, width=1)
        y += 8

        # Calendar grid - expand to fill available height
        cal = calendar.monthcalendar(today.year, today.month)
        num_weeks = len(cal)
        remaining_h = h - (y - 15)  # available height below header
        row_h = min(remaining_h // num_weeks, 65)
        cell_h = row_h

        for week in cal:
            for col_idx, day in enumerate(week):
                if day == 0:
                    continue

                cx = x + col_idx * cell_w
                cell_center_x = cx + cell_w // 2
                text_w = fonts["md"].getlength(str(day))
                text_x = cx + (cell_w - text_w) // 2

                if day == today.day:
                    # Filled circle for today
                    r = 16
                    draw.ellipse(
                        [cell_center_x - r, y + 4, cell_center_x + r, y + 4 + r * 2],
                        fill=0,
                    )
                    draw.text((text_x, y + 8), str(day), fill=255, font=fonts["md"])
                else:
                    draw.text((text_x, y + 8), str(day), fill=0, font=fonts["md"])

                # Event indicator dots below the day number
                num_events = event_day_counts.get(day, 0)
                if num_events > 0:
                    dot_count = min(num_events, 3)
                    dot_r = 2
                    dot_spacing = 7
                    dot_y = y + 28
                    total_w = dot_count * (dot_r * 2) + (dot_count - 1) * (dot_spacing - dot_r * 2)
                    dot_start_x = cell_center_x - total_w // 2
                    for di in range(dot_count):
                        dx = dot_start_x + di * dot_spacing
                        fill = 255 if day == today.day else 0
                        draw.ellipse([dx, dot_y, dx + dot_r * 2, dot_y + dot_r * 2], fill=fill)

            y += cell_h

    def _draw_events(self, draw, x, y, max_x, max_y, events, fonts):
        draw.text((x, y), "Upcoming Events", fill=0, font=fonts["lg"])
        y += 38

        if not events:
            msg = "No upcoming events"
            ics_hint = "Set an ICS URL in module settings"
            draw.text((x, y), msg, fill=120, font=fonts["md"])
            draw.text((x, y + 24), ics_hint, fill=160, font=fonts["sm"])
            return

        # Group events by date key for day indicator logic
        indicator_w = 32  # space reserved for the day circle on the left
        text_x = x + indicator_w + 8  # where event text starts
        entry_h = 48
        last_date_key = None

        for event in events:
            if y + entry_h > max_y:
                draw.text((text_x, y), "...", fill=100, font=fonts["md"])
                break

            dt = event["start"]
            date_key = dt.strftime("%Y-%m-%d")

            # Draw day circle only for first event of each day
            if date_key != last_date_key:
                day_str = str(dt.day)
                day_w = fonts["sm"].getlength(day_str)
                circle_r = 14
                circle_cx = x + indicator_w // 2
                circle_cy = y + 10
                draw.ellipse(
                    [circle_cx - circle_r, circle_cy - circle_r,
                     circle_cx + circle_r, circle_cy + circle_r],
                    outline=0, width=2,
                )
                draw.text(
                    (circle_cx - day_w // 2, circle_cy - 7),
                    day_str, fill=0, font=fonts["sm"],
                )
                last_date_key = date_key

            # Event title
            title = event["summary"]
            max_title_w = max_x - text_x
            if fonts["md"].getlength(title) > max_title_w:
                while fonts["md"].getlength(title + "...") > max_title_w and len(title) > 0:
                    title = title[:-1]
                title += "..."
            draw.text((text_x, y), title, fill=0, font=fonts["md"])

            # Time label
            if event["all_day"]:
                label = "All day"
            else:
                label = dt.strftime("%H:%M")
            draw.text((text_x, y + 20), label, fill=100, font=fonts["sm"])

            y += entry_h - 8
            draw.line([(text_x, y), (max_x, y)], fill=220, width=1)
            y += 8
