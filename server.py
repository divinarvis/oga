"""DIVINARVIS Portal V11 — Flask + upload + shared JSON sync + YouTube audio.

Render: deploy as a PYTHON WEB SERVICE (not as a Static Site).
Build: pip install -r requirements.txt
Start: gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 4 server:app

Important: local uploads/sync files are temporary on Render without persistent storage.
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
import re
import threading
import uuid
from functools import wraps
from hmac import compare_digest
from urllib.parse import parse_qs, urlsplit

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.utils import secure_filename

BASE = pathlib.Path(__file__).resolve().parent
DATA_DIR = pathlib.Path(os.environ.get("DIVINARVIS_DATA_DIR", str(BASE / "data")))
UPLOAD_DIR = DATA_DIR / "uploads"
SYNC_FILE = DATA_DIR / "sync.json"
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "100"))
PORTAL_TOKEN = os.environ.get("DIVINARVIS_TOKEN", "")
ALLOWED_EXTENSIONS = {
    ".mp3", ".m4a", ".mp4", ".aac", ".wav", ".ogg",
    ".opus", ".webm", ".flac", ".mov", ".png", ".jpg",
    ".jpeg", ".gif", ".webp", ".pdf",
}
PUBLIC_EXTENSIONS = {
    ".css", ".js", ".mjs", ".png", ".jpg", ".jpeg",
    ".gif", ".webp", ".svg", ".ico", ".woff", ".woff2",
    ".ttf", ".webmanifest", ".map",
}
SYNC_LOCK = threading.Lock()
YT_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024
app.json.ensure_ascii = False
app.logger.setLevel(logging.INFO)


def api_auth(view):
    """Require a bearer token if DIVINARVIS_TOKEN is configured."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if PORTAL_TOKEN:
            supplied = request.headers.get("Authorization", "")
            if not supplied.startswith("Bearer ") or not compare_digest(
                supplied[7:], PORTAL_TOKEN
            ):
                return jsonify({"ok": False, "error": "Accès refusé : jeton requis."}), 401
        return view(*args, **kwargs)
    return wrapped


def sync_read():
    if SYNC_FILE.is_file():
        try:
            with SYNC_FILE.open("r", encoding="utf-8") as fp:
                value = json.load(fp)
            return value if isinstance(value, dict) else {"action": "init"}
        except (OSError, json.JSONDecodeError):
            app.logger.warning("Impossible de lire sync.json")
    return {"action": "init"}


def sync_write(value: dict):
    temp_path = DATA_DIR / ("sync-" + uuid.uuid4().hex + ".tmp")
    try:
        with temp_path.open("w", encoding="utf-8") as fp:
            json.dump(value, fp, ensure_ascii=False)
        temp_path.replace(SYNC_FILE)
    finally:
        temp_path.unlink(missing_ok=True)


def youtube_watch_url(text: str) -> str | None:
    """Allow only normal YouTube links, never arbitrary download targets."""
    try:
        parsed = urlsplit(text.strip())
        hostname = (parsed.hostname or "").lower()
        if parsed.scheme not in ("http", "https"):
            return None
        if hostname in ("youtu.be", "www.youtu.be"):
            video_id = parsed.path.strip("/").split("/")[0]
        elif hostname in ("youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"):
            path = parsed.path.strip("/")
            if path == "watch":
                video_id = parse_qs(parsed.query).get("v", [""])[0]
            elif path.startswith(("shorts/", "live/", "embed/")):
                video_id = path.split("/")[1]
            else:
                return None
        else:
            return None
        return f"https://www.youtube.com/watch?v={video_id}" if YT_ID.fullmatch(video_id) else None
    except ValueError:
        return None


@app.route("/")
def index():
    if not (BASE / "index.html").is_file():
        return (
            "<h1>DIVINARVIS : index.html introuvable</h1>"
            "<p>Place index.html à côté de server.py.</p>",
            404,
        )
    return send_from_directory(BASE, "index.html")


@app.route("/assets/<path:filename>")
def assets(filename):
    return send_from_directory(BASE / "assets", filename)


@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(BASE / "static", filename)


@app.route("/<path:filename>")
def public_root_files(filename):
    # Only public file types; never expose server.py, cookies, sync.json, etc.
    if "/" in filename or pathlib.PurePosixPath(filename).suffix.lower() not in PUBLIC_EXTENSIONS:
        return jsonify({"ok": False, "error": "Fichier introuvable"}), 404
    return send_from_directory(BASE, filename)


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "service": "DIVINARVIS", "version": "11.0"})


@app.route("/api/sync", methods=["GET", "POST"])
@app.route("/api/portal/sync", methods=["GET", "POST"])
@api_auth
def sync():
    with SYNC_LOCK:
        if request.method == "GET":
            return jsonify(sync_read())
        value = request.get_json(silent=True)
        if not isinstance(value, dict):
            return jsonify({"ok": False, "error": "Objet JSON attendu"}), 400
        try:
            sync_write(value)
        except OSError:
            app.logger.exception("Erreur d'écriture de synchronisation")
            return jsonify({"ok": False, "error": "Enregistrement impossible"}), 500
        return jsonify(value)


@app.route("/uploads/<path:filename>", methods=["GET"])
def uploaded_file(filename):
    # Note: uploaded media are PUBLIC if the URL is known.
    return send_from_directory(UPLOAD_DIR, filename)


@app.route("/api/files", methods=["GET"])
@api_auth
def files():
    items = sorted(
        (f for f in UPLOAD_DIR.iterdir() if f.is_file() and f.suffix.lower() in ALLOWED_EXTENSIONS),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return jsonify([
        {"name": f.name, "url": "/uploads/" + f.name, "size": f.stat().st_size}
        for f in items
    ])


@app.route("/api/upload", methods=["POST"])
@api_auth
def upload():
    file = request.files.get("file")
    if file is None or not file.filename:
        return jsonify({"ok": False, "error": "Aucun fichier envoyé"}), 400
    filename = secure_filename(file.filename)
    ext = pathlib.Path(filename).suffix.lower()
    if not filename or ext not in ALLOWED_EXTENSIONS:
        return jsonify({"ok": False, "error": "Type de fichier non autorisé"}), 400
    unique_name = f"{uuid.uuid4().hex[:10]}_{filename}"
    try:
        file.save(UPLOAD_DIR / unique_name)
    except OSError:
        app.logger.exception("Erreur d'upload")
        return jsonify({"ok": False, "error": "Impossible d'enregistrer le fichier"}), 500
    return jsonify({"ok": True, "file": unique_name, "url": "/uploads/" + unique_name}), 201


@app.route("/api/delete", methods=["POST"])
@api_auth
def delete_file():
    data = request.get_json(silent=True)
    filename = data.get("file") if isinstance(data, dict) else None
    if not isinstance(filename, str) or not filename or filename != pathlib.Path(filename).name:
        return jsonify({"ok": False, "error": "Nom de fichier invalide"}), 400
    if pathlib.Path(filename).suffix.lower() not in ALLOWED_EXTENSIONS:
        return jsonify({"ok": False, "error": "Type de fichier non autorisé"}), 400
    target = UPLOAD_DIR / filename
    if not target.is_file():
        return jsonify({"ok": False, "error": "Fichier introuvable"}), 404
    try:
        target.unlink()
    except OSError:
        return jsonify({"ok": False, "error": "Suppression impossible"}), 500
    return jsonify({"ok": True})


@app.route("/api/youtube", methods=["POST"])
@api_auth
def youtube():
    data = request.get_json(silent=True)
    url = youtube_watch_url(data.get("url", "")) if isinstance(data, dict) and isinstance(data.get("url", ""), str) else None
    if not url:
        return jsonify({"ok": False, "error": "Lien YouTube invalide"}), 400

    # No FFmpeg required: prefer M4A, otherwise keep source audio format.
    # YouTube may reject server-side downloads; this feature isn't guaranteed.
    try:
        import yt_dlp

        opts = {
            "format": "bestaudio[ext=m4a]/bestaudio",
            "outtmpl": str(UPLOAD_DIR / "%(id)s.%(ext)s"),
            "noplaylist": True,
            "restrictfilenames": True,
            "max_filesize": MAX_UPLOAD_MB * 1024 * 1024,
            "quiet": True,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not isinstance(info, dict):
                raise ValueError("Aucune information vidéo")
            downloaded = pathlib.Path(ydl.prepare_filename(info)).name
            if not (UPLOAD_DIR / downloaded).is_file():
                raise ValueError("Fichier audio introuvable après téléchargement")
        return jsonify({
            "ok": True,
            "title": info.get("title", "Audio"),
            "file": downloaded,
            "url": "/uploads/" + downloaded,
        })
    except Exception as exc:
        app.logger.warning("Téléchargement YouTube impossible: %s", exc)
        return jsonify({
            "ok": False,
            "error": "Extraction audio impossible. Vérifie le lien et les restrictions YouTube/Render.",
        }), 502


@app.errorhandler(413)
def too_large(_error):
    return jsonify({"ok": False, "error": f"Fichier trop volumineux (limite : {MAX_UPLOAD_MB} Mo)"}), 413


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "10000")), debug=False)
