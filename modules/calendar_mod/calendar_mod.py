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

    def _get_event_days(self, events: list) -> set:
        """Get set of day numbers in the current month that have events."""
        today = datetime.now()
        days = set()
        for event in events:
            dt = event["start"]
            if dt.year == today.year and dt.month == today.month:
                days.add(dt.day)
        return days

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

        event_days = self._get_event_days(events)

        # Layout: left panel uses full height for month grid, right panel for events
        left_w = 300
        self._draw_month_grid(draw, 15, 15, left_w - 30, height - 30, event_days, fonts)

        # Vertical divider
        draw.line([(left_w, 10), (left_w, height - 10)], fill=180, width=1)

        # Right panel: events list
        self._draw_events(draw, left_w + 20, 15, width - 15, height - 15, events, fonts)

        return img

    def _draw_month_grid(self, draw, x, y, w, h, event_days, fonts):
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

                if day == today.day:
                    # Filled circle for today
                    r = 16
                    draw.ellipse(
                        [cell_center_x - r, y + 4, cell_center_x + r, y + 4 + r * 2],
                        fill=0,
                    )
                    draw.text(
                        (cx + (cell_w - text_w) // 2, y + 8),
                        str(day), fill=255, font=fonts["md"],
                    )
                elif day in event_days:
                    # Outlined circle for days with events
                    r = 16
                    draw.ellipse(
                        [cell_center_x - r, y + 4, cell_center_x + r, y + 4 + r * 2],
                        outline=0, width=2,
                    )
                    draw.text(
                        (cx + (cell_w - text_w) // 2, y + 8),
                        str(day), fill=0, font=fonts["md"],
                    )
                else:
                    draw.text(
                        (cx + (cell_w - text_w) // 2, y + 8),
                        str(day), fill=0, font=fonts["md"],
                    )

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

        entry_h = 54
        for event in events:
            if y + entry_h > max_y:
                draw.text((x, y), "...", fill=100, font=fonts["md"])
                break

            title = event["summary"]
            max_chars = int((max_x - x) / 8)
            if len(title) > max_chars:
                title = title[: max_chars - 3] + "..."
            draw.text((x, y), title, fill=0, font=fonts["md"])

            dt = event["start"]
            if event["all_day"]:
                label = dt.strftime("%a, %b %d  (all day)")
            else:
                label = dt.strftime("%a, %b %d  %H:%M")
            draw.text((x, y + 22), label, fill=100, font=fonts["sm"])

            y += entry_h - 8
            draw.line([(x, y), (max_x, y)], fill=220, width=1)
            y += 8
