import calendar
import logging
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw
from modules.base import BaseModule
from modules import theme

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
        }

    def _fetch_events(self, settings: dict) -> list:
        ics_url = settings.get("ics_url", "")
        if not ics_url:
            return []

        try:
            import requests
            from icalendar import Calendar

            tz = ZoneInfo(settings.get("_timezone", "Europe/Brussels"))

            response = requests.get(ics_url, timeout=15)
            response.raise_for_status()
            cal = Calendar.from_ical(response.text)

            now = datetime.now(tz)
            end = now + timedelta(days=int(settings.get("days_ahead", 7)))
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
                        dt = dt.replace(tzinfo=tz)
                    else:
                        dt = dt.astimezone(tz)
                    all_day = False
                else:
                    dt = datetime.combine(dt, datetime.min.time(), tzinfo=tz)
                    all_day = True

                if dt < end and dt >= now - timedelta(hours=1):
                    events.append({
                        "summary": str(component.get("summary", "Untitled")),
                        "start": dt,
                        "all_day": all_day,
                    })

            events.sort(key=lambda e: e["start"])
            return events

        except ImportError:
            logger.error("Install icalendar: pip install icalendar requests python-dateutil")
            return []
        except Exception as e:
            logger.error(f"Calendar fetch failed: {e}")
            return []

    def _get_event_day_counts(self, events: list, tz) -> dict:
        """Get dict of day number -> event count for the current month."""
        today = datetime.now(tz)
        counts = {}
        for event in events:
            dt = event["start"]
            if dt.year == today.year and dt.month == today.month:
                counts[dt.day] = counts.get(dt.day, 0) + 1
        return counts

    def _draw(self, width: int, height: int, events: list, settings: dict) -> Image.Image:
        img = Image.new("L", (width, height), theme.SURFACE)
        draw = ImageDraw.Draw(img)
        fonts = theme.load_fonts()

        tz = ZoneInfo(settings.get("_timezone", "Europe/Brussels"))
        event_day_counts = self._get_event_day_counts(events, tz)

        # Layout: two M3 surface-container cards — month grid on the left,
        # upcoming events on the right. A filled card at this size delta
        # (240 vs 255) is subtle on real e-ink, so pair it with a hairline
        # outline to keep each panel legible as its own region.
        outer_margin = 10
        left_w = 300
        gutter = 20
        pad = 15

        left_card = (outer_margin, outer_margin, left_w, height - outer_margin)
        right_card = (left_w + gutter, outer_margin, width - outer_margin, height - outer_margin)
        theme.draw_card(draw, left_card, fill=theme.SURFACE_CONTAINER, outline=theme.OUTLINE)
        theme.draw_card(draw, right_card, fill=theme.SURFACE_CONTAINER, outline=theme.OUTLINE)

        self._draw_month_grid(
            draw, left_card[0] + pad, left_card[1] + pad,
            (left_card[2] - left_card[0]) - pad * 2, (left_card[3] - left_card[1]) - pad * 2,
            event_day_counts, fonts, tz,
        )

        self._draw_events(
            draw, right_card[0] + pad, right_card[1] + pad,
            right_card[2] - pad, right_card[3] - pad, events, fonts,
        )

        return img

    def _draw_month_grid(self, draw, x, y, w, h, event_day_counts, fonts, tz=None):
        today = datetime.now(tz)
        start_y = y

        # Month/year header
        header = today.strftime("%B %Y")
        draw.text((x, y), header, fill=theme.ON_SURFACE, font=fonts["headline"])
        y += 42

        # Day-of-week headers
        days = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
        cell_w = w // 7
        for i, d in enumerate(days):
            cx = x + i * cell_w
            draw.text((cx + (cell_w - fonts["body"].getlength(d)) // 2, y), d, fill=theme.ON_SURFACE_VARIANT, font=fonts["body"])
        y += 24

        # Separator
        theme.draw_divider(draw, x, y, x + w)
        y += 8

        # Build calendar grid with neighbor month days filled in
        cal = calendar.monthcalendar(today.year, today.month)
        num_weeks = len(cal)
        remaining_h = h - (y - start_y)
        row_h = min(remaining_h // num_weeks, 65)
        cell_h = row_h

        # Figure out previous month's trailing days
        if today.month == 1:
            prev_year, prev_month = today.year - 1, 12
        else:
            prev_year, prev_month = today.year, today.month - 1
        prev_month_days = calendar.monthrange(prev_year, prev_month)[1]

        # Figure out next month starting days
        next_day_counter = 1

        for week_idx, week in enumerate(cal):
            for col_idx, day in enumerate(week):
                cx = x + col_idx * cell_w
                cell_center_x = cx + cell_w // 2

                if day == 0:
                    # Fill with previous or next month day (greyed out)
                    if week_idx == 0:
                        # First week: previous month days
                        # Count how many zeros before the first real day
                        first_real = next((i for i, d in enumerate(week) if d != 0), 7)
                        neighbor_day = prev_month_days - (first_real - 1 - col_idx)
                    else:
                        # Last week: next month days
                        neighbor_day = next_day_counter
                        next_day_counter += 1

                    text_w = fonts["body_lg"].getlength(str(neighbor_day))
                    text_x = cx + (cell_w - text_w) // 2
                    draw.text((text_x, y + 8), str(neighbor_day), fill=theme.OUTLINE, font=fonts["body_lg"])
                    continue

                text_w = fonts["body_lg"].getlength(str(day))
                text_x = cx + (cell_w - text_w) // 2

                if day == today.day:
                    # Filled circle for today
                    r = 16
                    draw.ellipse(
                        [cell_center_x - r, y + 4, cell_center_x + r, y + 4 + r * 2],
                        fill=theme.ON_SURFACE,
                    )
                    draw.text((text_x, y + 8), str(day), fill=theme.SURFACE, font=fonts["body_lg"])
                else:
                    draw.text((text_x, y + 8), str(day), fill=theme.ON_SURFACE, font=fonts["body_lg"])

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
                        fill = theme.SURFACE if day == today.day else theme.ON_SURFACE
                        draw.ellipse([dx, dot_y, dx + dot_r * 2, dot_y + dot_r * 2], fill=fill)

            y += cell_h

    def _draw_events(self, draw, x, y, max_x, max_y, events, fonts):
        draw.text((x, y), "Upcoming Events", fill=theme.ON_SURFACE, font=fonts["headline"])
        y += 30

        if not events:
            msg = "No upcoming events"
            ics_hint = "Set an ICS URL in module settings"
            draw.text((x, y), msg, fill=theme.ON_SURFACE_VARIANT, font=fonts["body_lg"])
            draw.text((x, y + 24), ics_hint, fill=theme.DISABLED, font=fonts["body"])
            return

        # Group events by date key for day indicator logic
        indicator_w = 32  # space reserved for the day circle on the left
        text_x = x + indicator_w + 8  # where event text starts
        entry_h = 44
        last_date_key = None
        last_month_key = None

        for event in events:
            dt = event["start"]
            month_key = dt.strftime("%Y-%m")
            date_key = dt.strftime("%Y-%m-%d")

            # Month separator when events cross into a new month
            if month_key != last_month_key and last_month_key is not None:
                if y + 16 + entry_h > max_y:
                    break
                month_label = dt.strftime("%B")
                theme.draw_divider(draw, x, y + 5, x + 8, tone=theme.DISABLED)
                mlw = fonts["label_sm"].getlength(month_label)
                draw.text((x + 12, y - 1), month_label, fill=theme.ON_SURFACE_VARIANT, font=fonts["label_sm"])
                theme.draw_divider(draw, x + 16 + mlw, y + 5, max_x, tone=theme.DISABLED)
                y += 14
            last_month_key = month_key

            if y + entry_h > max_y:
                draw.text((text_x, y), "…", fill=theme.ON_SURFACE_VARIANT, font=fonts["body_lg"])
                break

            # Draw day circle only for first event of each day
            if date_key != last_date_key:
                day_str = str(dt.day)
                day_w = fonts["body"].getlength(day_str)
                circle_r = 14
                circle_cx = x + indicator_w // 2
                circle_cy = y + 10
                draw.ellipse(
                    [circle_cx - circle_r, circle_cy - circle_r,
                     circle_cx + circle_r, circle_cy + circle_r],
                    outline=theme.ON_SURFACE, width=2,
                )
                draw.text(
                    (circle_cx - day_w // 2, circle_cy - 7),
                    day_str, fill=theme.ON_SURFACE, font=fonts["body"],
                )
                last_date_key = date_key

            # Event title
            title = theme.truncate_to_width(event["summary"], fonts["body_lg"], max_x - text_x)
            draw.text((text_x, y), title, fill=theme.ON_SURFACE, font=fonts["body_lg"])

            # Time chip
            label = "All day" if event["all_day"] else dt.strftime("%H:%M")
            theme.draw_chip(draw, (text_x, y + 19), label, fonts["label"],
                             align="left", valign="top", fill=theme.SURFACE_CONTAINER_HIGH)

            y += entry_h - 8
            theme.draw_divider(draw, text_x, y, max_x)
            y += 8
