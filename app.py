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
from modules.tasks.tasks import TasksModule
from modules.habits.habits import HabitsModule
from modules.fitness.fitness import FitnessModule

MODULE_REGISTRY = {
    PhotosModule.NAME: PhotosModule(),
    CalendarModule.NAME: CalendarModule(),
    TasksModule.NAME: TasksModule(),
    HabitsModule.NAME: HabitsModule(),
    FitnessModule.NAME: FitnessModule(),
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


def _clean_rotation(config, module_registry):
    """Remove any rotation entries that reference modules no longer in the registry."""
    rotation = config.rotation
    cleaned = [e for e in rotation if e.get("module") in module_registry]
    if len(cleaned) != len(rotation):
        removed = [e["module"] for e in rotation if e.get("module") not in module_registry]
        logger.warning(f"Removing unknown modules from rotation: {removed}")
        config.set(cleaned, "rotation")
        if cleaned:
            config.set(cleaned[0]["module"], "active_module")
        config.save()


def main():
    config = Config()
    _clean_rotation(config, MODULE_REGISTRY)
    display = DisplayDriver()
    renderer = Renderer(config, MODULE_REGISTRY, display)
    scheduler = Scheduler(
        render_module_fn=renderer.render_and_display,
        config=config,
    )

    scheduler.start()

    app = create_app(config, MODULE_REGISTRY, scheduler)
    logger.info("Starting EinkPi web UI on http://0.0.0.0:8080")
    app.run(host="0.0.0.0", port=8080, debug=False, threaded=True)


if __name__ == "__main__":
    main()
