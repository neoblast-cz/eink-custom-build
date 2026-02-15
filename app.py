import logging
import sys
from core.config import Config
from core.display import DisplayDriver
from core.scheduler import Scheduler
from core.renderer import Renderer
from web.routes import create_app

# ============================================================
# MODULE REGISTRY - Add new modules here (one line per module)
# ============================================================
from modules.photos.photos import PhotosModule
from modules.calendar_mod.calendar_mod import CalendarModule

MODULE_REGISTRY = {
    PhotosModule.NAME: PhotosModule(),
    CalendarModule.NAME: CalendarModule(),
    # To add a new module:
    # from modules.my_module.my_module import MyModule
    # MyModule.NAME: MyModule(),
}
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


def main():
    config = Config()
    display = DisplayDriver()
    renderer = Renderer(config, MODULE_REGISTRY, display)
    scheduler = Scheduler(
        refresh_callback=renderer.render_and_display,
        get_interval_fn=lambda: config.refresh_minutes,
    )

    scheduler.start()

    app = create_app(config, MODULE_REGISTRY, scheduler)
    logger.info("Starting EinkPi web UI on http://0.0.0.0:8080")
    app.run(host="0.0.0.0", port=8080, debug=False, threaded=True)


if __name__ == "__main__":
    main()
