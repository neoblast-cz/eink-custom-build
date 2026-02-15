import logging
import random
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps
from modules.base import BaseModule

logger = logging.getLogger(__name__)

PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"}


class PhotosModule(BaseModule):
    NAME = "photos"
    DISPLAY_NAME = "Photo Album"
    DESCRIPTION = "Rotates through your photos randomly, one per refresh"

    def __init__(self):
        self._shuffled_queue = []

    def render(self, width: int, height: int, settings: dict) -> Image.Image:
        photo_dir = Path(settings.get("photo_dir", "uploads"))
        if not photo_dir.exists():
            raise RuntimeError(f"Photo directory not found: {photo_dir}")

        photos = sorted(
            p for p in photo_dir.iterdir()
            if p.suffix.lower() in PHOTO_EXTENSIONS
        )

        if not photos:
            return self._no_photos_image(width, height)

        # Refill queue when empty - shuffle all photos, show each once before repeating
        if not self._shuffled_queue or not all(p in photos for p in self._shuffled_queue):
            self._shuffled_queue = list(photos)
            random.shuffle(self._shuffled_queue)

        photo_path = self._shuffled_queue.pop(0)
        logger.info(f"Displaying photo: {photo_path.name} ({len(photos) - len(self._shuffled_queue)}/{len(photos)})")
        mode = settings.get("display_mode", "fill")
        return self._render_photo(width, height, photo_path, mode)

    def default_settings(self) -> dict:
        return {"photo_dir": "uploads", "display_mode": "fill"}

    def _render_photo(self, width: int, height: int, path: Path, mode: str) -> Image.Image:
        try:
            photo = Image.open(path).convert("L")
        except Exception as e:
            raise RuntimeError(f"Failed to open {path.name}: {e}")

        if mode == "fill":
            # Crop to fill the entire screen (no letterboxing)
            return ImageOps.fit(photo, (width, height), Image.LANCZOS)
        else:
            # Fit within screen, letterbox with white
            photo.thumbnail((width, height), Image.LANCZOS)
            canvas = Image.new("L", (width, height), 255)
            x = (width - photo.width) // 2
            y = (height - photo.height) // 2
            canvas.paste(photo, (x, y))
            return canvas

    def _no_photos_image(self, width: int, height: int) -> Image.Image:
        img = Image.new("L", (width, height), 255)
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("arial.ttf", 20)
        except OSError:
            font = ImageFont.load_default()
        text = "No photos found. Upload some via the web UI!"
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        draw.text(((width - tw) // 2, height // 2 - 10), text, fill=0, font=font)
        return img
