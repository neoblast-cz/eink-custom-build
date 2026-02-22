import logging
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


class Renderer:
    def __init__(self, config, module_registry, display):
        self.config = config
        self.modules = module_registry
        self.display = display

    def render_and_display(self, module_name=None):
        if module_name is None:
            module_name = self.config.active_module
        module = self.modules.get(module_name)

        if module is None:
            logger.error(f"Unknown module: {module_name}")
            self._show_error(f"Unknown module: {module_name}")
            return

        settings = self.config.module_settings(module_name)
        if not settings:
            settings = module.default_settings()
        settings["_timezone"] = self.config.timezone
        if module_name == "tasks":
            settings["_habitica_settings"] = self.config.module_settings("habits")

        w = self.config.display_width
        h = self.config.display_height

        try:
            logger.info(f"Rendering module: {module_name}")
            image = module.render(w, h, settings)
            self.display.init()
            self.display.show(image)
            self.display.sleep()
            logger.info("Display updated successfully")
        except Exception as e:
            logger.exception(f"Error in module {module_name}")
            self._show_error(str(e))

    def _show_error(self, message: str):
        img = Image.new("L", (self.display.WIDTH, self.display.HEIGHT), 255)
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("arial.ttf", 18)
        except OSError:
            font = ImageFont.load_default()
        draw.text((20, 200), f"Error: {message}", fill=0, font=font)
        self.display.init()
        self.display.show(img)
        self.display.sleep()
