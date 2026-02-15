import re
import logging
from pathlib import Path
from flask import (
    Flask, render_template, request, redirect, url_for, jsonify, send_file,
)

logger = logging.getLogger(__name__)

UPLOAD_DIR = Path(__file__).parent.parent / "uploads"


def create_app(config, module_registry, scheduler):
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder=str(Path(__file__).parent.parent / "static"),
    )
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB upload limit

    @app.route("/")
    def index():
        return render_template(
            "index.html",
            active_module=config.active_module,
            modules=module_registry,
            refresh_minutes=config.refresh_minutes,
            rotation=config.rotation,
        )

    @app.route("/settings", methods=["GET", "POST"])
    def settings():
        if request.method == "POST":
            config.set(
                int(request.form.get("refresh_minutes", 30)),
                "display", "refresh_interval_minutes",
            )

            # Build rotation list from parallel form arrays
            rot_modules = request.form.getlist("rotation_module")
            rot_durations = request.form.getlist("rotation_duration")
            rotation = []
            for mod, dur in zip(rot_modules, rot_durations):
                rotation.append({
                    "module": mod,
                    "duration_minutes": int(dur) if dur else 5,
                })
            config.set(rotation, "rotation")

            # Set active_module to the first rotation entry for fallback
            if rotation:
                config.set(rotation[0]["module"], "active_module")

            config.save()
            return redirect(url_for("index"))

        rotation = config.rotation
        if not rotation:
            # Default: show current active module
            rotation = [{"module": config.active_module, "duration_minutes": config.refresh_minutes}]

        return render_template(
            "settings.html", config=config, modules=module_registry, rotation=rotation
        )

    @app.route("/module/<name>", methods=["GET", "POST"])
    def module_config(name):
        module = module_registry.get(name)
        if not module:
            return "Module not found", 404

        if request.method == "POST":
            new_settings = {}
            for key in request.form:
                new_settings[key] = request.form[key]
            config.set(new_settings, "modules", name)
            config.save()
            return redirect(url_for("index"))

        current_settings = config.module_settings(name)
        if not current_settings:
            current_settings = module.default_settings()

        return render_template(
            module.get_template_name(),
            module=module,
            settings=current_settings,
        )

    @app.route("/refresh", methods=["POST"])
    def refresh():
        scheduler.force_refresh()
        return jsonify({"status": "ok", "message": "Refresh triggered"})

    @app.route("/preview")
    def preview():
        preview_path = Path(__file__).parent.parent / "static" / "preview.png"
        if preview_path.exists():
            return send_file(preview_path, mimetype="image/png")
        return "No preview available", 404

    @app.route("/upload", methods=["POST"])
    def upload_photo():
        if "file" not in request.files:
            return jsonify({"error": "No file provided"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "Empty filename"}), 400

        UPLOAD_DIR.mkdir(exist_ok=True)
        safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", file.filename)
        file.save(UPLOAD_DIR / safe_name)
        return jsonify({"status": "ok", "filename": safe_name})

    @app.route("/photos")
    def photos_list():
        """List uploaded photos for management."""
        UPLOAD_DIR.mkdir(exist_ok=True)
        extensions = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"}
        photos = sorted(
            p.name for p in UPLOAD_DIR.iterdir()
            if p.suffix.lower() in extensions
        )
        return render_template("photos_manage.html", photos=photos)

    @app.route("/photos/delete/<filename>", methods=["POST"])
    def delete_photo(filename):
        safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", filename)
        path = UPLOAD_DIR / safe_name
        if path.exists():
            path.unlink()
        return redirect(url_for("photos_list"))

    return app
