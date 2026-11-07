import os
import random
import string
import secrets
from datetime import datetime, timedelta

from flask import (
    Flask, request, redirect, url_for,
    render_template, send_from_directory, abort, flash, session, jsonify
)

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

# Папка для файлов
UPLOAD_DIR = "/data/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Файл для текста админа
TEXT_FILE = "/data/admin_text.txt"
ADMIN_PASSWORD = "admin123" # <-- Поменяйте на свой пароль

# Хранилище кодов
CODES = {}
TTL = timedelta(hours=24)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024

def generate_code() -> str:
    while True:
        code = "".join(random.choices(string.digits, k=16))
        if code not in CODES:
            return code

def cleanup_expired():
    now = datetime.utcnow()
    expired = [c for c, m in CODES.items() if now - m["created_at"] > TTL]
    for code in expired:
        meta = CODES.pop(code, None)
        if meta:
            path = os.path.join(UPLOAD_DIR, meta["stored_name"])
            if os.path.exists(path):
                os.remove(path)

# --- ГЛАВНАЯ СТРАНИЦА ---
@app.route("/", methods=["GET", "POST"])
def index():
    cleanup_expired()

    if request.method == "POST":
        file = request.files.get("file")
        if not file or file.filename == "":
            flash("Выберите файл")
            return redirect(url_for("index"))

        code = generate_code()
        stored_name = f"{code}_{secrets.token_hex(8)}"
        save_path = os.path.join(UPLOAD_DIR, stored_name)
        
        file.save(save_path)

        CODES[code] = {
            "stored_name": stored_name,
            "original_name": file.filename,
            "created_at": datetime.utcnow(),
        }

        return render_template("index.html", new_code=code)

    return render_template("index.html")

@app.route("/d/<code>", methods=["GET"])
def download_page(code):
    cleanup_expired()
    meta = CODES.get(code)
    return render_template(
        "download.html",
        code=code,
        found=bool(meta),
        filename=meta["original_name"] if meta else None,
    )

@app.route("/d/<code>/file", methods=["GET"])
def download_file(code):
    cleanup_expired()
    meta = CODES.get(code)
    if not meta:
        abort(404)
    return send_from_directory(
        UPLOAD_DIR,
        meta["stored_name"],
        as_attachment=True,
        download_name=meta["original_name"],
    )

@app.route("/check", methods=["POST"])
def check_code():
    code = request.form.get("code", "").strip()
    if len(code) != 16 or not code.isdigit():
        flash("Код должен состоять из 16 цифр")
        return redirect(url_for("index"))
    return redirect(url_for("download_page", code=code))

# --- АДМИНКА ---
@app.route("/admin", methods=["GET", "POST"])
def admin():
    if not session.get("is_admin"):
        if request.method == "POST":
            if request.form.get("password") == ADMIN_PASSWORD:
                session["is_admin"] = True
                return redirect(url_for("admin"))
            flash("Неверный пароль")
        return render_template("admin_login.html")

    current_text = ""
    if os.path.exists(TEXT_FILE):
        with open(TEXT_FILE, "r", encoding="utf-8") as f:
            current_text = f.read()
    return render_template("admin_panel.html", text=current_text)

@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("index"))

@app.route("/api/text", methods=["GET"])
def get_text():
    if os.path.exists(TEXT_FILE):
        with open(TEXT_FILE, "r", encoding="utf-8") as f:
            return jsonify({"text": f.read()})
    return jsonify({"text": ""})

@app.route("/api/update_text", methods=["POST"])
def update_text():
    if not session.get("is_admin"):
        return jsonify({"error": "Unauthorized"}), 403
    new_text = request.json.get("text", "")
    with open(TEXT_FILE, "w", encoding="utf-8") as f:
        f.write(new_text)
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)