import os
import re
import logging
import urllib.error
from pathlib import Path

# Allow OAuth over HTTP for local/LAN use (no HTTPS on Pi)
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
from flask import (
    Flask, render_template, request, redirect, url_for, jsonify, send_file,
)
from web import analytics_data
from web import finance_data

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
        return render_template(
            "index.html",
            active_module=config.active_module,
            modules=module_registry,
            refresh_minutes=config.refresh_minutes,
            config=config,
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
            return redirect(url_for("settings"))

        rotation = config.rotation
        if not rotation:
            rotation = [{"module": config.active_module, "duration_minutes": config.refresh_minutes}]

        return render_template(
            "settings.html",
            modules=module_registry,
            rotation=rotation,
            config=config,
            timezones=COMMON_TIMEZONES,
        )

    @app.route("/permissions", methods=["GET", "POST"])
    def permissions():
        if request.method == "POST":
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

            # Google credentials (used by the local-only Finance dashboard)
            g_id = request.form.get("google_client_id", "").strip()
            g_secret = request.form.get("google_client_secret", "").strip()
            g_redirect = request.form.get("google_redirect_uri", "").strip()
            if g_id:
                config.set(g_id, "google", "client_id")
            if g_secret:
                config.set(g_secret, "google", "client_secret")
            if g_redirect:
                config.set(g_redirect, "google", "redirect_uri")

            config.save()
            return redirect(url_for("permissions"))

        return render_template(
            "permissions.html",
            config=config,
            habitica_settings=config.module_settings("habits"),
            finance_authorized=finance_data.available(config),
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

    # ---- Local-only health data analytics (reads the gitignored "Google Health"
    # export folder; not part of the e-ink rendering pipeline or the Pi deploy) ----

    @app.route("/analytics")
    def analytics():
        if not analytics_data.available():
            return render_template("analytics.html", has_data=False)
        return render_template("analytics.html", has_data=True, **analytics_data.get_dashboard_data())

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
            "scope": "activity heartrate weight profile sleep",
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

    # ---- Local-only financial dashboard, backed by a live Google Sheet.
    # Not part of the e-ink rendering pipeline or the Pi deploy. ----

    @app.route("/finance")
    def finance():
        """Serves the React+MUI single-page app shell — all real data comes
        from /finance/api/data, fetched client-side after mount."""
        return render_template("finance_app.html")

    @app.route("/finance/api/data")
    def finance_api_data():
        spreadsheet_id = config.get("finance", "spreadsheet_id", default="")
        authorized = finance_data.is_authorized()

        if not spreadsheet_id or not authorized:
            return jsonify({
                "has_data": False,
                "spreadsheet_configured": bool(spreadsheet_id),
                "google_authorized": authorized,
            })
        try:
            data = finance_data.get_dashboard_data(config)
        except finance_data.NotAuthorized:
            return jsonify({
                "has_data": False,
                "spreadsheet_configured": bool(spreadsheet_id),
                "google_authorized": False,
            })
        except Exception as e:
            logger.error(f"Finance dashboard fetch failed: {e}")
            return jsonify({
                "has_data": False,
                "spreadsheet_configured": bool(spreadsheet_id),
                "google_authorized": authorized,
                "fetch_error": str(e),
            })
        return jsonify({"has_data": True, **data})

    @app.route("/finance/api/spreadsheet", methods=["POST"])
    def finance_api_spreadsheet():
        """Save the spreadsheet URL/ID pasted on the not-authorized setup screen."""
        body = request.get_json(silent=True) or {}
        raw = (body.get("spreadsheet_url") or "").strip()
        # Accept either a bare ID or a full /d/<id>/ URL.
        match = re.search(r"/d/([a-zA-Z0-9-_]+)", raw)
        spreadsheet_id = match.group(1) if match else raw
        if spreadsheet_id:
            config.set(spreadsheet_id, "finance", "spreadsheet_id")
            config.save()
        return jsonify({"ok": True})

    @app.route("/finance/api/snapshot", methods=["POST"])
    def finance_api_snapshot():
        """On-demand: append a row of headline numbers, plus a link to a
        full-page dashboard screenshot uploaded to Drive, to a "Snapshot"
        tab in the user's own spreadsheet. Needs the read-write Sheets
        scope (and drive.file for the screenshot) — a token issued before
        those scopes were added will 403 on the Sheets write, reported
        distinctly (re-authorize in Permissions) rather than as a generic
        failure. A Drive-only failure doesn't reach here — save_snapshot
        catches it internally so the numbers row still saves regardless,
        and reports it back via screenshot_error instead."""
        try:
            result = finance_data.save_snapshot(config, request.host_url)
            return jsonify({"ok": True, **result})
        except finance_data.NotAuthorized as e:
            return jsonify({"ok": False, "error": str(e)}), 401
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            logger.error(f"Finance snapshot write failed: {e.code} {body}")
            if e.code == 403:
                return jsonify({
                    "ok": False,
                    "error": "insufficient_scope",
                    "message": "Google Sheets is only authorized for read access. Re-authorize in Permissions to allow writing a snapshot.",
                }), 403
            return jsonify({"ok": False, "error": f"Google Sheets error: {e.code}"}), 502
        except Exception as e:
            logger.error(f"Finance snapshot write failed: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500

    # ---- Google OAuth for the Finance dashboard's Sheets access ----

    @app.route("/oauth/google_sheets/start")
    def oauth_google_sheets_start():
        """Redirect straight to Google's consent screen. Unlike Fitbit, Google
        allows plain-HTTP localhost redirect URIs, so this can be a real
        automatic redirect instead of a manual copy-paste flow."""
        import urllib.parse as _urlparse

        client_id = config.get("google", "client_id", default="")
        redirect_uri = config.get(
            "google", "redirect_uri",
            default="http://localhost:8080/oauth/google_sheets/callback",
        )
        if not client_id:
            return "Set Google credentials in Permissions first", 400

        params = _urlparse.urlencode({
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            # Read-write Sheets (not .readonly) for appending snapshot rows,
            # plus drive.file (not full Drive access) for uploading visual
            # snapshot screenshots — drive.file only grants access to files
            # this app itself creates, never the rest of the user's Drive.
            # Existing tokens issued under an older/narrower scope won't
            # gain the new access on refresh; re-authorizing is required.
            "scope": "https://www.googleapis.com/auth/spreadsheets https://www.googleapis.com/auth/drive.file",
            "access_type": "offline",
            "prompt": "consent",
        })
        return redirect(f"https://accounts.google.com/o/oauth2/v2/auth?{params}")

    @app.route("/oauth/google_sheets/callback")
    def oauth_google_sheets_callback():
        """Google redirects here with ?code=... directly (no manual paste needed)."""
        import json as json_mod
        import urllib.request as _urlreq
        import urllib.parse as _urlparse
        import urllib.error as _urlerr
        import time

        error = request.args.get("error")
        if error:
            return f"Google authorization failed: {error}", 400

        code = request.args.get("code", "").strip()
        if not code:
            return "No authorization code received", 400

        client_id = config.get("google", "client_id", default="")
        client_secret = config.get("google", "client_secret", default="")
        redirect_uri = config.get(
            "google", "redirect_uri",
            default="http://localhost:8080/oauth/google_sheets/callback",
        )
        if not client_id or not client_secret:
            return "Google credentials not configured", 400

        data = _urlparse.urlencode({
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
        }).encode()

        req = _urlreq.Request(
            "https://oauth2.googleapis.com/token",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        try:
            with _urlreq.urlopen(req, timeout=15) as resp:
                token_data = json_mod.loads(resp.read())

            token_data["expires_at"] = time.time() + token_data.get("expires_in", 3600)
            finance_data.save_token(token_data)

            logger.info("Google Sheets authorized successfully")
            return redirect(url_for("finance"))
        except _urlerr.HTTPError as e:
            error_body = e.read().decode()
            logger.error(f"Google token exchange failed: {e.code} {error_body}")
            return f"Google returned {e.code}: {error_body}", 400
        except Exception as e:
            logger.error(f"Google token exchange error: {e}")
            return str(e), 500

    return app
