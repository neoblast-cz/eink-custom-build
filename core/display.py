import logging
from pathlib import Path
from PIL import Image

logger = logging.getLogger(__name__)

PREVIEW_PATH = Path(__file__).parent.parent / "static" / "preview.png"


class DisplayDriver:
    """
    Thin wrapper around Waveshare EPD7in5 V2 driver.
    Falls back to saving preview PNGs when hardware is unavailable (Windows dev).
    """

    WIDTH = 800
    HEIGHT = 480

    def __init__(self):
        self._epd = None
        self._available = False
        self._try_import()

    def _try_import(self):
        try:
            from waveshare_epd import epd7in5_V2
            self._epd = epd7in5_V2.EPD()
            self._available = True
            logger.info("Waveshare EPD driver loaded")
        except ImportError:
            logger.warning(
                "Waveshare EPD not available - running in preview-only mode"
            )
        except Exception as e:
            logger.error(f"EPD import failed: {e}")

    def init(self):
        if self._available:
            self._epd.init()

    def clear(self):
        if self._available:
            self._epd.Clear()

    def show(self, image: Image.Image):
        """Display a PIL Image on the e-ink screen and save a preview PNG."""
        if image.size != (self.WIDTH, self.HEIGHT):
            image = image.resize((self.WIDTH, self.HEIGHT), Image.LANCZOS)

        bw_image = image.convert("1")

        # Save preview for web UI
        PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
        image.convert("L").save(PREVIEW_PATH)

        if self._available:
            self._epd.display(self._epd.getbuffer(bw_image))
            logger.info("Display updated")
        else:
            logger.info(f"Preview-only mode: image saved to {PREVIEW_PATH}")

    def sleep(self):
        if self._available:
            self._epd.sleep()

    def close(self):
        if self._available:
            try:
                from waveshare_epd import epdconfig
                epdconfig.module_exit(cleanup=True)
            except Exception as e:
                logger.error(f"EPD cleanup failed: {e}")
