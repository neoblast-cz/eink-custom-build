import os
import re
import logging
from pathlib import Path

# Allow OAuth over HTTP for local/LAN use (no HTTPS on Pi)
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
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

        extra = {}
        if name == "tasks":
            token_path = Path(__file__).parent.parent / "google_token.json"
            extra["authorized"] = token_path.exists()

        return render_template(
            module.get_template_name(),
            module=module,
            settings=current_settings,
            **extra,
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

    @app.route("/preview_module/<name>", methods=["POST"])
    def preview_module(name):
        """Render a module to preview without pushing to the e-ink display."""
        from core.renderer import Renderer
        module = module_registry.get(name)
        if not module:
            return jsonify({"error": "Module not found"}), 404

        settings = config.module_settings(name)
        if not settings:
            settings = module.default_settings()

        try:
            image = module.render(config.display_width, config.display_height, settings)
            preview_path = Path(__file__).parent.parent / "static" / "preview.png"
            preview_path.parent.mkdir(parents=True, exist_ok=True)
            image.convert("L").save(preview_path)
            return jsonify({"status": "ok"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/photos/thumbnail/<filename>")
    def photo_thumbnail(filename):
        """Serve a thumbnail of an uploaded photo."""
        safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", filename)
        path = UPLOAD_DIR / safe_name
        if not path.exists():
            return "Not found", 404

        from PIL import Image as PILImage
        import io
        img = PILImage.open(path)
        img.thumbnail((200, 200))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=70)
        buf.seek(0)
        return send_file(buf, mimetype="image/jpeg")

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

    # ---- Google OAuth routes for Tasks module ----

    @app.route("/oauth/google/start")
    def oauth_google_start():
        """Start Google OAuth flow for Tasks API."""
        try:
            from google_auth_oauthlib.flow import Flow
        except ImportError:
            return "google-auth-oauthlib not installed. Run: pip install google-auth-oauthlib", 500

        settings = config.module_settings("tasks") or {}
        client_id = settings.get("client_id", "")
        client_secret = settings.get("client_secret", "")

        if not client_id or not client_secret:
            return redirect(url_for("module_config", name="tasks"))

        client_config = {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [f"http://{request.host}/oauth/google/callback"],
            }
        }

        flow = Flow.from_client_config(
            client_config,
            scopes=["https://www.googleapis.com/auth/tasks.readonly"],
            redirect_uri=f"http://{request.host}/oauth/google/callback",
        )

        auth_url, _ = flow.authorization_url(
            access_type="offline",
            prompt="consent",
        )
        return redirect(auth_url)

    @app.route("/oauth/google/callback")
    def oauth_google_callback():
        """Handle Google OAuth callback, save tokens."""
        try:
            from google_auth_oauthlib.flow import Flow
        except ImportError:
            return "google-auth-oauthlib not installed", 500

        settings = config.module_settings("tasks") or {}
        client_id = settings.get("client_id", "")
        client_secret = settings.get("client_secret", "")

        client_config = {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [f"http://{request.host}/oauth/google/callback"],
            }
        }

        flow = Flow.from_client_config(
            client_config,
            scopes=["https://www.googleapis.com/auth/tasks.readonly"],
            redirect_uri=f"http://{request.host}/oauth/google/callback",
        )

        flow.fetch_token(authorization_response=request.url)

        creds = flow.credentials
        token_path = Path(__file__).parent.parent / "google_token.json"
        token_path.write_text(creds.to_json())
        logger.info("Google Tasks authorized successfully")

        return redirect(url_for("module_config", name="tasks"))

    @app.route("/tasks/lists")
    def tasks_lists():
        """Return JSON list of user's Google Task lists."""
        token_path = Path(__file__).parent.parent / "google_token.json"
        if not token_path.exists():
            return jsonify({"error": "Not authorized"}), 401

        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build

            creds = Credentials.from_authorized_user_file(
                str(token_path),
                ["https://www.googleapis.com/auth/tasks.readonly"],
            )
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                token_path.write_text(creds.to_json())

            service = build("tasks", "v1", credentials=creds)
            results = service.tasklists().list(maxResults=20).execute()
            items = results.get("items", [])
            return jsonify({
                "lists": [{"id": l["id"], "title": l["title"]} for l in items]
            })
        except Exception as e:
            logger.error(f"Failed to fetch task lists: {e}")
            return jsonify({"error": str(e)}), 500

    return app
