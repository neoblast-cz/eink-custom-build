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

COMMON_TIMEZONES = [
    "Europe/Brussels", "Europe/London", "Europe/Paris", "Europe/Berlin",
    "Europe/Amsterdam", "Europe/Prague", "Europe/Rome", "Europe/Madrid",
    "Europe/Zurich", "Europe/Vienna", "Europe/Warsaw", "Europe/Stockholm",
    "Europe/Helsinki", "Europe/Athens", "Europe/Bucharest", "Europe/Moscow",
    "US/Eastern", "US/Central", "US/Mountain", "US/Pacific",
    "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles",
    "America/Toronto", "America/Sao_Paulo",
    "Asia/Tokyo", "Asia/Shanghai", "Asia/Singapore", "Asia/Kolkata",
    "Asia/Dubai", "Asia/Seoul",
    "Australia/Sydney", "Australia/Melbourne",
    "Pacific/Auckland",
    "UTC",
]


def create_app(config, module_registry, scheduler):
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder=str(Path(__file__).parent.parent / "static"),
    )
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB upload limit

    @app.route("/")
    def index():
        rotation = config.rotation
        if not rotation:
            rotation = [{"module": config.active_module, "duration_minutes": config.refresh_minutes}]

        return render_template(
            "index.html",
            active_module=config.active_module,
            modules=module_registry,
            refresh_minutes=config.refresh_minutes,
            rotation=rotation,
            config=config,
            timezones=COMMON_TIMEZONES,
            habitica_settings=config.module_settings("habits"),
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

            # Timezone
            tz = request.form.get("timezone", "Europe/Brussels")
            config.set(tz, "display", "timezone")

            config.save()
            return redirect(url_for("index"))

        # Settings are now inline on the dashboard
        return redirect(url_for("index"))

    @app.route("/permissions", methods=["POST"])
    def permissions():
        # Google API credentials
        g_id = request.form.get("google_client_id", "").strip()
        g_secret = request.form.get("google_client_secret", "").strip()
        if g_id:
            config.set(g_id, "google", "client_id")
        if g_secret:
            config.set(g_secret, "google", "client_secret")

        # Habitica credentials (stored in habits module settings)
        hab_user = request.form.get("habitica_user_id", "").strip()
        hab_token = request.form.get("habitica_api_token", "").strip()
        habits_settings = config.module_settings("habits") or {}
        habits_settings["habitica_user_id"] = hab_user
        habits_settings["habitica_api_token"] = hab_token
        config.set(habits_settings, "modules", "habits")

        # Fitbit credentials
        fb_id = request.form.get("fitbit_client_id", "").strip()
        fb_secret = request.form.get("fitbit_client_secret", "").strip()
        fb_redirect = request.form.get("fitbit_redirect_uri", "").strip()
        if fb_id:
            config.set(fb_id, "fitbit", "client_id")
        if fb_secret:
            config.set(fb_secret, "fitbit", "client_secret")
        if fb_redirect:
            config.set(fb_redirect, "fitbit", "redirect_uri")

        config.save()
        return redirect(url_for("index"))

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
        if name == "fitness":
            token_path = Path(__file__).parent.parent / "fitbit_token.json"
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
        settings["_timezone"] = config.timezone
        if name == "tasks":
            settings["_habitica_settings"] = config.module_settings("habits")
        if name == "fitness":
            settings["_fitbit_client_id"] = config.get("fitbit", "client_id", default="")
            settings["_fitbit_client_secret"] = config.get("fitbit", "client_secret", default="")

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

        client_id = config.google_client_id
        client_secret = config.google_client_secret

        if not client_id or not client_secret:
            return "Set up Google API credentials in Settings first.", 400

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

        client_id = config.google_client_id
        client_secret = config.google_client_secret

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

    # ---- Fitbit OAuth routes for Fitness module ----

    @app.route("/oauth/fitbit/auth_url")
    def oauth_fitbit_auth_url():
        """Return JSON with the Fitbit authorization URL."""
        import urllib.parse as _urlparse

        client_id = config.get("fitbit", "client_id", default="")
        redirect_uri = config.get(
            "fitbit", "redirect_uri",
            default="https://raspberrypi:8080/oauth/fitbit/callback",
        )

        if not client_id:
            return jsonify({"error": "Set Fitbit credentials in Permissions first"}), 400

        params = _urlparse.urlencode({
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": "activity heartrate weight profile",
            "expires_in": "604800",
        })
        url = f"https://www.fitbit.com/oauth2/authorize?{params}"
        return jsonify({"url": url})

    @app.route("/oauth/fitbit/exchange", methods=["POST"])
    def oauth_fitbit_exchange():
        """Exchange authorization code for access + refresh tokens."""
        import base64
        import json as json_mod
        import urllib.request as _urlreq
        import urllib.parse as _urlparse
        import urllib.error as _urlerr
        import time

        code = request.form.get("code", "").strip()
        # Handle pasted full URL or code with fragment suffix
        if "code=" in code:
            code = code.split("code=")[-1]
        code = code.split("#")[0].split("&")[0].strip()
        if not code:
            return jsonify({"error": "No code provided"}), 400

        client_id = config.get("fitbit", "client_id", default="")
        client_secret = config.get("fitbit", "client_secret", default="")
        redirect_uri = config.get(
            "fitbit", "redirect_uri",
            default="https://raspberrypi:8080/oauth/fitbit/callback",
        )

        if not client_id or not client_secret:
            return jsonify({"error": "Fitbit credentials not configured"}), 400

        auth_header = base64.b64encode(
            f"{client_id}:{client_secret}".encode()
        ).decode()
        data = _urlparse.urlencode({
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        }).encode()

        req = _urlreq.Request(
            "https://api.fitbit.com/oauth2/token",
            data=data,
            headers={
                "Authorization": f"Basic {auth_header}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )

        try:
            with _urlreq.urlopen(req, timeout=15) as resp:
                token_data = json_mod.loads(resp.read())

            token_data["expires_at"] = time.time() + token_data.get("expires_in", 28800)
            token_path = Path(__file__).parent.parent / "fitbit_token.json"
            token_path.write_text(json_mod.dumps(token_data, indent=2))

            logger.info("Fitbit authorized successfully")
            return jsonify({"status": "ok"})
        except _urlerr.HTTPError as e:
            error_body = e.read().decode()
            logger.error(f"Fitbit token exchange failed: {e.code} {error_body}")
            return jsonify({"error": f"Fitbit returned {e.code}: {error_body}"}), 400
        except Exception as e:
            logger.error(f"Fitbit token exchange error: {e}")
            return jsonify({"error": str(e)}), 500

    return app
