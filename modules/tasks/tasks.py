import json
import logging
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont
from modules.base import BaseModule

logger = logging.getLogger(__name__)

HABITICA_API = "https://habitica.com/api/v3"


class TasksModule(BaseModule):
    NAME = "tasks"
    DISPLAY_NAME = "Tasks"
    DESCRIPTION = "Shows Habitica to-dos"

    def render(self, width: int, height: int, settings: dict) -> Image.Image:
        todos = self._fetch_habitica_todos(settings)
        return self._draw(width, height, todos, settings)

    def default_settings(self) -> dict:
        return {
            "max_tasks": 15,
            "show_completed": "",
        }

    def _fetch_habitica_todos(self, settings: dict) -> list:
        hab = settings.get("_habitica_settings", {})
        user_id = hab.get("habitica_user_id", "")
        api_token = hab.get("habitica_api_token", "")

        if not user_id or not api_token:
            return []

        try:
            url = f"{HABITICA_API}/tasks/user?type=todos"
            req = urllib.request.Request(url, headers={
                "x-api-user": user_id,
                "x-api-key": api_token,
                "x-client": f"{user_id}-EinkPi",
                "Content-Type": "application/json",
            })

            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read())

            if not result.get("success"):
                logger.error(f"Habitica API error: {result}")
                return []

            todos = []
            for item in result["data"]:
                title = item.get("text", "").strip()
                if not title:
                    continue

                due = None
                if item.get("date"):
                    try:
                        due = datetime.fromisoformat(item["date"].replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        pass

                todos.append({
                    "title": title,
                    "status": "completed" if item.get("completed", False) else "needsAction",
                    "due": due,
                })

            todos.sort(key=lambda t: (
                0 if t["status"] == "needsAction" else 1,
                0 if t["due"] else 1,
                t["due"] or datetime.max,
            ))
            return todos

        except Exception as e:
            logger.error(f"Habitica todos fetch failed: {e}")
            return []

    def _load_fonts(self):
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
            "C:/Windows/Fonts/segoeuib.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]
        fonts = {}
        for size_name, size in [("lg", 26), ("md", 17), ("sm", 13), ("sub", 15)]:
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

    def _draw(self, width: int, height: int, todos: list, settings: dict) -> Image.Image:
        img = Image.new("L", (width, height), 255)
        draw = ImageDraw.Draw(img)
        fonts = self._load_fonts()

        margin = 20
        y = margin

        # Title bar
        draw.text((margin, y), "Tasks", fill=0, font=fonts["lg"])
        tz = ZoneInfo(settings.get("_timezone", "Europe/Brussels"))
        date_str = datetime.now(tz).strftime("%a, %b %d")
        date_w = fonts["md"].getlength(date_str)
        draw.text((width - margin - date_w, y + 4), date_str, fill=100, font=fonts["md"])
        y += 40

        draw.line([(margin, y), (width - margin, y)], fill=0, width=2)
        y += 8

        hab = settings.get("_habitica_settings", {})
        has_creds = bool(hab.get("habitica_user_id")) and bool(hab.get("habitica_api_token"))

        self._draw_task_list(
            draw, todos,
            x=margin, y=y,
            w=width - 2 * margin,
            h=height - y - margin,
            fonts=fonts,
            empty_msg="Not configured" if not has_creds else "No to-dos",
            empty_hint="Set Habitica credentials in Habits settings" if not has_creds else None,
        )

        return img

    def _draw_task_list(self, draw, tasks, x, y, w, h, fonts,
                        empty_msg="No tasks", empty_hint=None):
        row_h = 32
        checkbox_size = 12
        max_y = y + h

        if not tasks:
            draw.text((x, y), empty_msg, fill=80, font=fonts["md"])
            if empty_hint:
                draw.text((x, y + 24), empty_hint, fill=120, font=fonts["sm"])
            return

        incomplete = [t for t in tasks if t["status"] == "needsAction"]
        completed = [t for t in tasks if t["status"] == "completed"]

        cy = y
        max_title_w = w - checkbox_size - 16

        for task in incomplete:
            if cy + row_h > max_y:
                draw.text((x, cy), "...", fill=100, font=fonts["md"])
                return

            bx, by = x, cy + 2
            draw.rectangle([bx, by, bx + checkbox_size, by + checkbox_size], outline=0, width=2)

            due_str = ""
            due_w = 0
            if task.get("due"):
                due_str = task["due"].strftime("%b %d")
                due_w = fonts["sm"].getlength(due_str) + 8

            title = task["title"]
            text_x = x + checkbox_size + 8
            avail_w = max_title_w - due_w
            if fonts["md"].getlength(title) > avail_w:
                while fonts["md"].getlength(title + "..") > avail_w and len(title) > 1:
                    title = title[:-1]
                title += ".."
            draw.text((text_x, cy - 1), title, fill=0, font=fonts["md"])

            if due_str:
                draw.text((x + w - due_w + 4, cy + 1), due_str, fill=100, font=fonts["sm"])

            cy += row_h

        if completed:
            if cy + row_h + 10 >= max_y:
                return

            cy += 4
            label = " Done "
            label_w = fonts["sm"].getlength(label)
            line_y = cy + 7
            center = x + w // 2
            draw.line([(x, line_y), (center - label_w // 2 - 3, line_y)], fill=180, width=1)
            draw.text((center - label_w // 2, cy), label, fill=150, font=fonts["sm"])
            draw.line([(center + label_w // 2 + 3, line_y), (x + w, line_y)], fill=180, width=1)
            cy += 22

            for task in completed:
                if cy + row_h > max_y:
                    break

                bx, by = x, cy + 2
                draw.rectangle([bx, by, bx + checkbox_size, by + checkbox_size],
                                outline=100, fill=200, width=2)
                draw.line([(bx + 2, by + 6), (bx + 5, by + 9)], fill=60, width=2)
                draw.line([(bx + 5, by + 9), (bx + 10, by + 2)], fill=60, width=2)

                title = task["title"]
                text_x = x + checkbox_size + 8
                if fonts["md"].getlength(title) > max_title_w:
                    while fonts["md"].getlength(title + "..") > max_title_w and len(title) > 1:
                        title = title[:-1]
                    title += ".."
                draw.text((text_x, cy - 1), title, fill=150, font=fonts["md"])
                title_w = fonts["md"].getlength(title)
                draw.line([(text_x, cy + 8), (text_x + title_w, cy + 8)], fill=150, width=1)

                cy += row_h
