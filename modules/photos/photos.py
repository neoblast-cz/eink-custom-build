import logging
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps
from modules.base import BaseModule

logger = logging.getLogger(__name__)

PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"}


class PhotosModule(BaseModule):
    NAME = "photos"
    DISPLAY_NAME = "Photo Album"
    DESCRIPTION = "Rotates through your photos, one per refresh"

    def __init__(self):
        self._current_index = 0

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

        # Wrap index around
        self._current_index = self._current_index % len(photos)
        photo_path = photos[self._current_index]
        self._current_index += 1

        logger.info(f"Displaying photo: {photo_path.name}")
        return self._render_photo(width, height, photo_path)

    def default_settings(self) -> dict:
        return {"photo_dir": "uploads"}

    def _render_photo(self, width: int, height: int, path: Path) -> Image.Image:
        """Load, fit to display size, and center on white background."""
        try:
            photo = Image.open(path).convert("L")
        except Exception as e:
            raise RuntimeError(f"Failed to open {path.name}: {e}")

        # Fit photo to display while maintaining aspect ratio
        photo.thumbnail((width, height), Image.LANCZOS)

        # Center on white canvas
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
