import json
import logging
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw
from modules.base import BaseModule
from modules import theme

logger = logging.getLogger(__name__)

HABITICA_API = "https://habitica.com/api/v3"


class TasksModule(BaseModule):
    NAME = "tasks"
    DISPLAY_NAME = "Tasks"
    DESCRIPTION = "Shows Habitica to-dos"

    def render(self, width: int, height: int, settings: dict) -> Image.Image:
        todos = self._fetch_habitica_todos(settings)
        if not settings.get("show_completed"):
            todos = [t for t in todos if t["status"] != "completed"]
        max_tasks = int(settings.get("max_tasks", 15) or 15)
        todos = todos[:max_tasks]
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

    def _draw(self, width: int, height: int, todos: list, settings: dict) -> Image.Image:
        img = Image.new("L", (width, height), theme.SURFACE)
        draw = ImageDraw.Draw(img)
        fonts = theme.load_fonts()

        margin = 20
        y = margin

        # Title bar
        draw.text((margin, y), "Tasks", fill=theme.ON_SURFACE, font=fonts["headline"])
        tz = ZoneInfo(settings.get("_timezone", "Europe/Brussels"))
        date_str = datetime.now(tz).strftime("%a, %b %d")
        date_w = fonts["body_lg"].getlength(date_str)
        draw.text((width - margin - date_w, y + 4), date_str, fill=theme.ON_SURFACE_VARIANT, font=fonts["body_lg"])
        y += 40

        theme.draw_divider(draw, margin, y, width - margin)
        y += 16

        pad = 15
        theme.draw_card(draw, (margin, y, width - margin, height - margin),
                         fill=theme.SURFACE_CONTAINER, outline=theme.OUTLINE)

        hab = settings.get("_habitica_settings", {})
        has_creds = bool(hab.get("habitica_user_id")) and bool(hab.get("habitica_api_token"))

        self._draw_task_list(
            draw, todos,
            x=margin + pad, y=y + pad,
            w=width - 2 * (margin + pad),
            h=height - margin - pad - (y + pad),
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
            draw.text((x, y), empty_msg, fill=theme.ON_SURFACE_VARIANT, font=fonts["body_lg"])
            if empty_hint:
                draw.text((x, y + 24), empty_hint, fill=theme.DISABLED, font=fonts["body"])
            return

        incomplete = [t for t in tasks if t["status"] == "needsAction"]
        completed = [t for t in tasks if t["status"] == "completed"]

        cy = y
        max_title_w = w - checkbox_size - 16

        for task in incomplete:
            if cy + row_h > max_y:
                draw.text((x, cy), "…", fill=theme.ON_SURFACE_VARIANT, font=fonts["body_lg"])
                return

            bx, by = x, cy + 2
            draw.rounded_rectangle([bx, by, bx + checkbox_size, by + checkbox_size],
                                    radius=theme.RADIUS_XS, outline=theme.ON_SURFACE, width=2)

            due_str = ""
            due_w = 0
            if task.get("due"):
                due_str = task["due"].strftime("%b %d")
                due_w = fonts["label"].getlength(due_str) + theme.SPACE_SM * 2

            title = task["title"]
            text_x = x + checkbox_size + 8
            avail_w = max_title_w - due_w
            title = theme.truncate_to_width(title, fonts["body_lg"], avail_w)
            draw.text((text_x, cy - 1), title, fill=theme.ON_SURFACE, font=fonts["body_lg"])

            if due_str:
                theme.draw_chip(draw, (x + w, cy - 1), due_str, fonts["label"],
                                 align="right", valign="top", fill=theme.SURFACE_CONTAINER_HIGH)

            cy += row_h

        if completed:
            if cy + row_h + 10 >= max_y:
                return

            cy += 4
            label = " Done "
            label_w = fonts["body"].getlength(label)
            line_y = cy + 7
            center = x + w // 2
            theme.draw_divider(draw, x, line_y, center - label_w // 2 - 3)
            draw.text((center - label_w // 2, cy), label, fill=theme.DISABLED, font=fonts["body"])
            theme.draw_divider(draw, center + label_w // 2 + 3, line_y, x + w)
            cy += 22

            for task in completed:
                if cy + row_h > max_y:
                    break

                bx, by = x, cy + 2
                draw.rounded_rectangle([bx, by, bx + checkbox_size, by + checkbox_size],
                                        radius=theme.RADIUS_XS,
                                        outline=theme.ON_SURFACE_VARIANT, fill=theme.SURFACE_CONTAINER_HIGH, width=2)
                draw.line([(bx + 2, by + 6), (bx + 5, by + 9)], fill=theme.ON_SURFACE_VARIANT, width=2)
                draw.line([(bx + 5, by + 9), (bx + 10, by + 2)], fill=theme.ON_SURFACE_VARIANT, width=2)

                title = theme.truncate_to_width(task["title"], fonts["body_lg"], max_title_w)
                text_x = x + checkbox_size + 8
                draw.text((text_x, cy - 1), title, fill=theme.DISABLED, font=fonts["body_lg"])
                title_w = fonts["body_lg"].getlength(title)
                draw.line([(text_x, cy + 8), (text_x + title_w, cy + 8)], fill=theme.DISABLED, width=1)

                cy += row_h
