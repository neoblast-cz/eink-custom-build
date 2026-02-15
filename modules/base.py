from PIL import Image


class BaseModule:
    """
    Base class for all EinkPi display modules.

    To create a new module:
    1. Create modules/my_module/my_module.py
    2. Define a class inheriting BaseModule
    3. Implement render(self, width, height, settings) -> PIL.Image
    4. Create web/templates/modules/my_module.html for the config form
    5. Add one import + one dict entry in app.py MODULE_REGISTRY
    """

    NAME = "base"
    DISPLAY_NAME = "Base"
    DESCRIPTION = ""

    def render(self, width: int, height: int, settings: dict) -> Image.Image:
        """
        Return a PIL Image of exactly width x height.
        The display driver handles B&W conversion.
        """
        raise NotImplementedError

    def default_settings(self) -> dict:
        """Return default settings for first-time setup."""
        return {}

    def get_template_name(self) -> str:
        """Return the Jinja2 template path for this module's config form."""
        return f"modules/{self.NAME}.html"
