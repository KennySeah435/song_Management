from flask import Flask, jsonify, request, render_template, send_from_directory
import sqlite3
import os
from werkzeug.utils import secure_filename
from datetime import datetime

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "songs.db")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

SHEET_EXTS = {"pdf", "png", "jpg", "jpeg"}
AUDIO_EXTS = {"mp3", "wav", "m4a", "ogg", "aac", "flac"}
FILE_FIELDS = ["chord_sheet", "lead_sheet", "jianpu", "audio"]


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS songs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                title_zh    TEXT,
                key         TEXT,
                beats       TEXT,
                chord_sheet TEXT,
                lead_sheet  TEXT,
                jianpu      TEXT,
                audio       TEXT,
                youtube_url TEXT,
                remark      TEXT,
                created_at  TEXT
            )
        """)


init_db()


def ext_of(filename):
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def allowed(filename, field):
    e = ext_of(filename)
    return e in (AUDIO_EXTS if field == "audio" else SHEET_EXTS)


def save_upload(file, field, song_id):
    if not file or not file.filename:
        return None
    if not allowed(file.filename, field):
        return None
    filename = secure_filename(f"{song_id}_{field}.{ext_of(file.filename)}")
    file.save(os.path.join(UPLOAD_DIR, filename))
    return filename


def remove_upload(filename):
    if filename:
        path = os.path.join(UPLOAD_DIR, filename)
        if os.path.exists(path):
            os.remove(path)


@app.route("/")
def index():
    return render_template("songs.html")


@app.route("/songs", methods=["GET"])
def get_songs():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM songs ORDER BY title COLLATE NOCASE").fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/songs", methods=["POST"])
def add_song():
    title = (request.form.get("title") or "").strip()
    if not title:
        return jsonify({"error": "Title is required"}), 400

    row = {
        "title":       title,
        "title_zh":    (request.form.get("title_zh") or "").strip(),
        "key":         (request.form.get("key") or "").strip(),
        "beats":       (request.form.get("beats") or "").strip(),
        "chord_sheet": None,
        "lead_sheet":  None,
        "jianpu":      None,
        "audio":       None,
        "youtube_url": (request.form.get("youtube_url") or "").strip(),
        "remark":      (request.form.get("remark") or "").strip(),
        "created_at":  datetime.now().strftime("%Y-%m-%d %H:%M"),
    }

    with get_db() as conn:
        cur = conn.execute("""
            INSERT INTO songs (title,title_zh,key,beats,chord_sheet,lead_sheet,jianpu,audio,youtube_url,remark,created_at)
            VALUES (:title,:title_zh,:key,:beats,:chord_sheet,:lead_sheet,:jianpu,:audio,:youtube_url,:remark,:created_at)
        """, row)
        song_id = cur.lastrowid

    updates = {}
    for field in FILE_FIELDS:
        name = save_upload(request.files.get(field), field, song_id)
        if name:
            updates[field] = name

    if updates:
        set_clause = ", ".join(f"{k}=?" for k in updates)
        with get_db() as conn:
            conn.execute(f"UPDATE songs SET {set_clause} WHERE id=?",
                         list(updates.values()) + [song_id])

    with get_db() as conn:
        r = conn.execute("SELECT * FROM songs WHERE id=?", (song_id,)).fetchone()
    return jsonify(dict(r)), 201


@app.route("/songs/<int:song_id>", methods=["PUT"])
def update_song(song_id):
    with get_db() as conn:
        existing = conn.execute("SELECT * FROM songs WHERE id=?", (song_id,)).fetchone()
    if not existing:
        return jsonify({"error": "Song not found"}), 404
    existing = dict(existing)

    title = (request.form.get("title") or "").strip()
    if not title:
        return jsonify({"error": "Title is required"}), 400

    row = {
        "title":       title,
        "title_zh":    (request.form.get("title_zh") or "").strip(),
        "key":         (request.form.get("key") or "").strip(),
        "beats":       (request.form.get("beats") or "").strip(),
        "youtube_url": (request.form.get("youtube_url") or "").strip(),
        "remark":      (request.form.get("remark") or "").strip(),
        "id":          song_id,
    }

    for field in FILE_FIELDS:
        new_file = request.files.get(field)
        if new_file and new_file.filename:
            remove_upload(existing[field])
            row[field] = save_upload(new_file, field, song_id) or existing[field]
        elif request.form.get(f"clear_{field}") == "1":
            remove_upload(existing[field])
            row[field] = None
        else:
            row[field] = existing[field]

    with get_db() as conn:
        conn.execute("""
            UPDATE songs SET title=:title,title_zh=:title_zh,key=:key,beats=:beats,
            chord_sheet=:chord_sheet,lead_sheet=:lead_sheet,jianpu=:jianpu,audio=:audio,
            youtube_url=:youtube_url,remark=:remark WHERE id=:id
        """, row)
        r = conn.execute("SELECT * FROM songs WHERE id=?", (song_id,)).fetchone()
    return jsonify(dict(r))


@app.route("/songs/<int:song_id>", methods=["DELETE"])
def delete_song(song_id):
    with get_db() as conn:
        existing = conn.execute("SELECT * FROM songs WHERE id=?", (song_id,)).fetchone()
    if not existing:
        return jsonify({"error": "Song not found"}), 404
    existing = dict(existing)
    for field in FILE_FIELDS:
        remove_upload(existing.get(field))
    with get_db() as conn:
        conn.execute("DELETE FROM songs WHERE id=?", (song_id,))
    return jsonify({"deleted": song_id})


@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    return send_from_directory(UPLOAD_DIR, filename)


if __name__ == "__main__":
    app.run(debug=True, port=5001)
