import json
import logging
import os
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont
from modules.base import BaseModule

logger = logging.getLogger(__name__)

TOKEN_PATH = Path(__file__).parent.parent.parent / "google_token.json"
SCOPES = ["https://www.googleapis.com/auth/tasks.readonly"]
HABITICA_API = "https://habitica.com/api/v3"


class TasksModule(BaseModule):
    NAME = "tasks"
    DISPLAY_NAME = "Tasks"
    DESCRIPTION = "Shows Google Tasks and Habitica to-dos side by side"

    def render(self, width: int, height: int, settings: dict) -> Image.Image:
        google_tasks = self._fetch_tasks(settings)
        habitica_todos = self._fetch_habitica_todos(settings)
        return self._draw(width, height, google_tasks, habitica_todos, settings)

    def default_settings(self) -> dict:
        return {
            "list_id": "@default",
            "max_tasks": 15,
            "show_completed": "",
        }

    def _get_google_service(self, settings: dict):
        """Build an authenticated Google Tasks API service."""
        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build
        except ImportError:
            logger.error("Install google libs: pip install google-auth-oauthlib google-api-python-client")
            return None

        if not TOKEN_PATH.exists():
            logger.warning("Google Tasks not authorized. Visit the Tasks settings page to authorize.")
            return None

        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                TOKEN_PATH.write_text(creds.to_json())

            return build("tasks", "v1", credentials=creds)
        except Exception as e:
            logger.error(f"Google Tasks auth failed: {e}")
            return None

    def _fetch_tasks(self, settings: dict) -> list:
        service = self._get_google_service(settings)
        if not service:
            return []

        list_id = settings.get("list_id", "@default") or "@default"
        max_tasks = int(settings.get("max_tasks", 15))
        show_completed = settings.get("show_completed") in ("on", "true", True, "1")

        try:
            results = service.tasks().list(
                tasklist=list_id,
                maxResults=max_tasks,
                showCompleted=show_completed,
                showHidden=show_completed,
            ).execute()

            items = results.get("items", [])
            tasks = []
            for item in items:
                title = item.get("title", "").strip()
                if not title:
                    continue

                due = None
                if item.get("due"):
                    try:
                        due = datetime.fromisoformat(item["due"].replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        pass

                tasks.append({
                    "title": title,
                    "status": item.get("status", "needsAction"),
                    "due": due,
                })

            tasks.sort(key=lambda t: (
                0 if t["status"] == "needsAction" else 1,
                0 if t["due"] else 1,
                t["due"] or datetime.max,
            ))
            return tasks

        except Exception as e:
            logger.error(f"Google Tasks fetch failed: {e}")
            return []

    def _fetch_habitica_todos(self, settings: dict) -> list:
        """Fetch incomplete and completed to-dos from Habitica API."""
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

            # Sort: incomplete first, then by due date
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

    def _draw(self, width: int, height: int, google_tasks: list,
              habitica_todos: list, settings: dict) -> Image.Image:
        img = Image.new("L", (width, height), 255)
        draw = ImageDraw.Draw(img)
        fonts = self._load_fonts()

        margin = 20
        y = margin

        # Title bar (full width)
        draw.text((margin, y), "Tasks", fill=0, font=fonts["lg"])
        tz = ZoneInfo(settings.get("_timezone", "Europe/Brussels"))
        date_str = datetime.now(tz).strftime("%a, %b %d")
        date_w = fonts["md"].getlength(date_str)
        draw.text((width - margin - date_w, y + 4), date_str, fill=100, font=fonts["md"])
        y += 40

        # Full-width separator
        draw.line([(margin, y), (width - margin, y)], fill=0, width=2)
        y += 8

        # Split into two halves
        mid_x = width // 2
        left_x = margin
        left_w = mid_x - margin - 5
        right_x = mid_x + 5
        right_w = width - margin - right_x

        # Vertical divider
        draw.line([(mid_x, y), (mid_x, height - margin)], fill=180, width=1)

        # Sub-headers
        draw.text((left_x, y), "Google Tasks", fill=80, font=fonts["sub"])
        draw.text((right_x, y), "Habitica", fill=80, font=fonts["sub"])
        y += 24

        # Thin separator under sub-headers
        draw.line([(left_x, y), (mid_x - 5, y)], fill=180, width=1)
        draw.line([(right_x, y), (width - margin, y)], fill=180, width=1)
        y += 8

        # Draw task lists in each half
        hab = settings.get("_habitica_settings", {})
        has_habitica_creds = bool(hab.get("habitica_user_id")) and bool(hab.get("habitica_api_token"))

        self._draw_task_list(
            draw, google_tasks, left_x, y, left_w, height - y - margin, fonts,
            empty_msg="Not authorized" if not TOKEN_PATH.exists() else "No tasks",
            empty_hint="Open Tasks settings to connect Google" if not TOKEN_PATH.exists() else None,
        )
        self._draw_task_list(
            draw, habitica_todos, right_x, y, right_w, height - y - margin, fonts,
            empty_msg="Not configured" if not has_habitica_creds else "No to-dos",
            empty_hint="Set Habitica credentials in Habits settings" if not has_habitica_creds else None,
        )

        return img

    def _draw_task_list(self, draw, tasks, x, y, w, h, fonts,
                        empty_msg="No tasks", empty_hint=None):
        """Draw a list of tasks (checkboxes + titles) within a bounded area."""
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

        # Incomplete tasks
        for task in incomplete:
            if cy + row_h > max_y:
                draw.text((x, cy), "...", fill=100, font=fonts["md"])
                return

            # Empty checkbox
            bx, by = x, cy + 2
            draw.rectangle(
                [bx, by, bx + checkbox_size, by + checkbox_size],
                outline=0, width=2,
            )

            # Due date string (if available)
            due_str = ""
            due_w = 0
            if task.get("due"):
                due_str = task["due"].strftime("%b %d")
                due_w = fonts["sm"].getlength(due_str) + 8

            # Title (truncate if needed, accounting for due date width)
            title = task["title"]
            text_x = x + checkbox_size + 8
            avail_w = max_title_w - due_w
            if fonts["md"].getlength(title) > avail_w:
                while fonts["md"].getlength(title + "..") > avail_w and len(title) > 1:
                    title = title[:-1]
                title += ".."
            draw.text((text_x, cy - 1), title, fill=0, font=fonts["md"])

            # Draw due date to the right
            if due_str:
                draw.text((x + w - due_w + 4, cy + 1), due_str, fill=100, font=fonts["sm"])

            cy += row_h

        # Completed section
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

                # Checked checkbox
                bx, by = x, cy + 2
                draw.rectangle(
                    [bx, by, bx + checkbox_size, by + checkbox_size],
                    outline=100, fill=200, width=2,
                )
                # Checkmark
                draw.line([(bx + 2, by + 6), (bx + 5, by + 9)], fill=60, width=2)
                draw.line([(bx + 5, by + 9), (bx + 10, by + 2)], fill=60, width=2)

                # Strikethrough title
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
