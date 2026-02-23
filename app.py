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
from modules.dashboard.dashboard import DashboardModule
from modules.habits.habits import HabitsModule
from modules.fitness.fitness import FitnessModule

MODULE_REGISTRY = {
    PhotosModule.NAME: PhotosModule(),
    CalendarModule.NAME: CalendarModule(),
    TasksModule.NAME: TasksModule(),
    DashboardModule.NAME: DashboardModule(),
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


def main():
    config = Config()
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
