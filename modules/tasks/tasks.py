import json
import logging
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont
from modules.base import BaseModule

logger = logging.getLogger(__name__)

TOKEN_PATH = Path(__file__).parent.parent.parent / "google_token.json"
SCOPES = ["https://www.googleapis.com/auth/tasks.readonly"]


class TasksModule(BaseModule):
    NAME = "tasks"
    DISPLAY_NAME = "Tasks"
    DESCRIPTION = "Shows your Google Tasks on the display"

    def render(self, width: int, height: int, settings: dict) -> Image.Image:
        tasks = self._fetch_tasks(settings)
        return self._draw(width, height, tasks, settings)

    def default_settings(self) -> dict:
        return {
            "client_id": "",
            "client_secret": "",
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
                    continue  # skip blank tasks

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

            # Sort: incomplete first, then dated before dateless, then by due date
            tasks.sort(key=lambda t: (
                0 if t["status"] == "needsAction" else 1,
                0 if t["due"] else 1,
                t["due"] or datetime.max,
            ))
            return tasks

        except Exception as e:
            logger.error(f"Google Tasks fetch failed: {e}")
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
        for size_name, size in [("lg", 26), ("md", 17), ("sm", 13)]:
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

    def _draw(self, width: int, height: int, tasks: list, settings: dict) -> Image.Image:
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

        # Separator
        draw.line([(margin, y), (width - margin, y)], fill=0, width=2)
        y += 15

        if not tasks:
            if not TOKEN_PATH.exists():
                draw.text((margin, y), "Not authorized", fill=80, font=fonts["md"])
                draw.text((margin, y + 28), "Open Tasks settings in the web UI to connect", fill=120, font=fonts["sm"])
                draw.text((margin, y + 48), "your Google account.", fill=120, font=fonts["sm"])
            else:
                draw.text((margin, y), "No tasks found", fill=80, font=fonts["md"])
            return img

        # Split into incomplete and completed
        incomplete = [t for t in tasks if t["status"] == "needsAction"]
        completed = [t for t in tasks if t["status"] == "completed"]

        row_h = 36
        checkbox_size = 14

        # Draw incomplete tasks
        for task in incomplete:
            if y + row_h > height - margin:
                draw.text((margin, y), "...", fill=100, font=fonts["md"])
                break

            # Empty checkbox
            cx, cy = margin, y + 2
            draw.rectangle(
                [cx, cy, cx + checkbox_size, cy + checkbox_size],
                outline=0, width=2,
            )

            # Title
            title = task["title"]
            max_title_w = width - margin * 2 - 30 - 120
            text_x = margin + checkbox_size + 12
            if fonts["md"].getlength(title) > max_title_w:
                while fonts["md"].getlength(title + "...") > max_title_w and len(title) > 0:
                    title = title[:-1]
                title += "..."
            draw.text((text_x, y - 1), title, fill=0, font=fonts["md"])

            # Due date (or "No date" for dateless tasks)
            if task["due"]:
                due_str = f"Due: {task['due'].strftime('%a %d')}"
                draw.text((width - margin - fonts["sm"].getlength(due_str), y + 1),
                           due_str, fill=100, font=fonts["sm"])

            y += row_h

        # Draw completed section
        if completed:
            if y + row_h + 10 < height - margin:
                y += 5
                label = " Completed "
                label_w = fonts["sm"].getlength(label)
                line_y = y + 7
                draw.line([(margin, line_y), (width // 2 - label_w // 2 - 5, line_y)], fill=180, width=1)
                draw.text((width // 2 - label_w // 2, y), label, fill=150, font=fonts["sm"])
                draw.line([(width // 2 + label_w // 2 + 5, line_y), (width - margin, line_y)], fill=180, width=1)
                y += 25

                for task in completed:
                    if y + row_h > height - margin:
                        break

                    # Checked checkbox
                    cx, cy = margin, y + 2
                    draw.rectangle(
                        [cx, cy, cx + checkbox_size, cy + checkbox_size],
                        outline=100, fill=200, width=2,
                    )
                    # Checkmark
                    draw.line([(cx + 3, cy + 7), (cx + 6, cy + 11)], fill=60, width=2)
                    draw.line([(cx + 6, cy + 11), (cx + 12, cy + 3)], fill=60, width=2)

                    # Strikethrough title
                    title = task["title"]
                    text_x = margin + checkbox_size + 12
                    max_title_w = width - margin * 2 - 30
                    if fonts["md"].getlength(title) > max_title_w:
                        while fonts["md"].getlength(title + "...") > max_title_w and len(title) > 0:
                            title = title[:-1]
                        title += "..."
                    draw.text((text_x, y - 1), title, fill=150, font=fonts["md"])
                    # Strikethrough line
                    title_w = fonts["md"].getlength(title)
                    draw.line([(text_x, y + 8), (text_x + title_w, y + 8)], fill=150, width=1)

                    y += row_h

        return img
