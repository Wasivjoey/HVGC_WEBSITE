"""Harbour View Gospel Chapel — public website + simple content manager.

Sermon files and photos are stored in the database (Postgres or SQLite) so they
persist across deploys and can be browsed in the gallery.

Run locally:   python3 app.py     →  http://localhost:5000
Production:    gunicorn 'app:create_app()' --bind 0.0.0.0:5000
"""

import os
import re
import mimetypes
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for, flash, session, abort,
    Response,
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from db import get_db, init_db, now_iso, get_settings, execute_returning_id

ALLOWED_IMAGE = {"png", "jpg", "jpeg", "gif", "webp"}
ALLOWED_DOC = {"pdf", "ppt", "pptx", "key", "odp", "png", "jpg", "jpeg"}


# --------------------------------------------------------------------- helpers
def youtube_embed(url):
    if not url:
        return ""
    url = url.strip()
    m = re.search(r"(?:youtube\.com/(?:watch\?v=|embed/|live/|shorts/)|youtu\.be/)([A-Za-z0-9_-]{11})", url)
    if m:
        return f"https://www.youtube.com/embed/{m.group(1)}"
    return url


def slugify(text):
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s or "post"


def unique_slug(conn, text, post_id=None):
    base = slugify(text)
    slug, n = base, 1
    while True:
        row = conn.execute(
            "SELECT id FROM posts WHERE slug = ? AND id IS NOT ?", (slug, post_id)
        ).fetchone()
        if row is None:
            return slug
        n += 1
        slug = f"{base}-{n}"


def _ext(filename):
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def save_media(conn, file_storage, allowed):
    """Store an uploaded file's bytes in the media table. Returns (media_id, original_name)."""
    if file_storage is None or not file_storage.filename:
        return None, None
    if _ext(file_storage.filename) not in allowed:
        raise ValueError("Sorry, that file type isn't allowed.")
    data = file_storage.read()
    if not data:
        return None, None
    content_type = file_storage.mimetype or mimetypes.guess_type(file_storage.filename)[0] \
        or "application/octet-stream"
    media_id = execute_returning_id(
        conn,
        "INSERT INTO media (content_type, filename, data, created_at) VALUES (?, ?, ?, ?)",
        (content_type, secure_filename(file_storage.filename), data, now_iso()),
    )
    return media_id, file_storage.filename


def delete_media(conn, media_id):
    if media_id:
        conn.execute("DELETE FROM media WHERE id = ?", (media_id,))


def login_required(view):
    @wraps(view)
    def wrapped(*a, **k):
        if not session.get("admin"):
            return redirect(url_for("admin_login"))
        return view(*a, **k)
    return wrapped


def send_email(to_address, subject, body):
    host = os.environ.get("SMTP_HOST")
    if not host or not to_address:
        print(f"[email not sent — SMTP not configured] To: {to_address} | {subject}")
        return False
    import smtplib
    from email.message import EmailMessage
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.environ.get("SMTP_FROM", os.environ.get("SMTP_USER", "no-reply@hvgc.local"))
    msg["To"] = to_address
    msg.set_content(body)
    try:
        with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587")), timeout=15) as s:
            if os.environ.get("SMTP_TLS", "1") != "0":
                s.starttls()
            if os.environ.get("SMTP_USER"):
                s.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASSWORD", ""))
            s.send_message(msg)
        return True
    except Exception as e:
        print("email failed:", e)
        return False


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-change-me")
    app.config["MAX_CONTENT_LENGTH"] = 30 * 1024 * 1024
    init_db()

    @app.context_processor
    def inject():
        conn = get_db()
        s = get_settings(conn)
        conn.close()
        return {"S": s, "is_admin": bool(session.get("admin"))}

    @app.template_filter("yt")
    def yt(url):
        return youtube_embed(url)

    @app.template_filter("nl2br")
    def nl2br(text):
        from markupsafe import Markup, escape
        return Markup("<br>".join(escape(text or "").split("\n")))

    @app.template_filter("pretty")
    def pretty(value):
        from datetime import datetime
        try:
            return datetime.strptime(value[:19], "%Y-%m-%dT%H:%M:%S").strftime("%B %-d, %Y")
        except (ValueError, TypeError):
            return value

    @app.template_filter("nicedate")
    def nicedate(value):
        from datetime import datetime
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").strftime("%A, %B %-d, %Y")
        except (ValueError, TypeError):
            return value

    @app.template_filter("evmon")
    def evmon(value):
        from datetime import datetime
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").strftime("%b")
        except (ValueError, TypeError):
            return ""

    @app.template_filter("evday")
    def evday(value):
        from datetime import datetime
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").strftime("%-d")
        except (ValueError, TypeError):
            return ""

    # --------------------------------------------------------------- media
    @app.route("/media/<int:media_id>")
    def media(media_id):
        conn = get_db()
        row = conn.execute(
            "SELECT content_type, filename, data FROM media WHERE id = ?", (media_id,)
        ).fetchone()
        conn.close()
        if row is None:
            abort(404)
        data = bytes(row["data"])
        resp = Response(data, mimetype=row["content_type"] or "application/octet-stream")
        if row["filename"]:
            resp.headers["Content-Disposition"] = f'inline; filename="{row["filename"]}"'
        resp.headers["Cache-Control"] = "public, max-age=86400"
        return resp

    # --------------------------------------------------------------- public
    @app.route("/")
    def home():
        from datetime import date
        conn = get_db()
        posts = conn.execute(
            "SELECT * FROM posts WHERE published = 1 ORDER BY created_at DESC LIMIT 3"
        ).fetchall()
        gallery = conn.execute(
            "SELECT * FROM gallery ORDER BY created_at DESC LIMIT 8"
        ).fetchall()
        presentations = conn.execute(
            "SELECT * FROM presentations ORDER BY created_at DESC LIMIT 6"
        ).fetchall()
        events = conn.execute(
            "SELECT * FROM events WHERE event_date >= ? ORDER BY event_date, event_time LIMIT 4",
            (date.today().isoformat(),),
        ).fetchall()
        conn.close()
        return render_template("public/index.html", posts=posts, gallery=gallery,
                               presentations=presentations, events=events)

    @app.route("/gallery")
    def gallery():
        conn = get_db()
        items = conn.execute("SELECT * FROM gallery ORDER BY created_at DESC").fetchall()
        conn.close()
        return render_template("public/gallery.html", items=items)

    @app.route("/sermons")
    def sermons():
        conn = get_db()
        items = conn.execute("SELECT * FROM presentations ORDER BY created_at DESC").fetchall()
        conn.close()
        return render_template("public/sermons.html", items=items)

    @app.route("/events")
    def events():
        from datetime import date
        conn = get_db()
        upcoming = conn.execute(
            "SELECT * FROM events WHERE event_date >= ? ORDER BY event_date, event_time",
            (date.today().isoformat(),),
        ).fetchall()
        conn.close()
        return render_template("public/events.html", upcoming=upcoming)

    @app.route("/blog")
    def blog():
        conn = get_db()
        posts = conn.execute(
            "SELECT * FROM posts WHERE published = 1 ORDER BY created_at DESC"
        ).fetchall()
        conn.close()
        return render_template("public/blog.html", posts=posts)

    @app.route("/blog/<slug>")
    def post(slug):
        conn = get_db()
        p = conn.execute("SELECT * FROM posts WHERE slug = ? AND published = 1", (slug,)).fetchone()
        conn.close()
        if p is None:
            abort(404)
        return render_template("public/post.html", p=p)

    @app.route("/contact", methods=["POST"])
    def contact():
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        body = request.form.get("message", "").strip()
        if not name or not body:
            flash("Please add your name and a message.", "warning")
            return redirect(url_for("home") + "#contact")
        conn = get_db()
        conn.execute("INSERT INTO messages (name, email, body, created_at) VALUES (?, ?, ?, ?)",
                     (name, email, body, now_iso()))
        church_email = conn.execute("SELECT value FROM settings WHERE key = 'contact_email'").fetchone()
        conn.commit()
        conn.close()
        if church_email and church_email["value"]:
            send_email(church_email["value"], f"Website message from {name}",
                       f"From: {name} <{email}>\n\n{body}")
        flash("Thank you! Your message has been sent.", "success")
        return redirect(url_for("home") + "#contact")

    @app.route("/healthz")
    def healthz():
        return {"status": "ok"}, 200

    # ------------------------------------------------------------------ admin
    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        if session.get("admin"):
            return redirect(url_for("admin_dashboard"))
        if request.method == "POST":
            conn = get_db()
            u = conn.execute("SELECT * FROM users WHERE username = ?",
                             (request.form.get("username", "").strip(),)).fetchone()
            conn.close()
            if u and check_password_hash(u["password_hash"], request.form.get("password", "")):
                session["admin"] = u["username"]
                return redirect(url_for("admin_dashboard"))
            flash("Incorrect username or password.", "danger")
        return render_template("admin/login.html")

    @app.route("/admin/logout")
    def admin_logout():
        session.clear()
        return redirect(url_for("admin_login"))

    @app.route("/admin")
    @login_required
    def admin_dashboard():
        conn = get_db()
        counts = {
            "posts": conn.execute("SELECT COUNT(*) AS c FROM posts").fetchone()["c"],
            "gallery": conn.execute("SELECT COUNT(*) AS c FROM gallery").fetchone()["c"],
            "presentations": conn.execute("SELECT COUNT(*) AS c FROM presentations").fetchone()["c"],
            "events": conn.execute("SELECT COUNT(*) AS c FROM events").fetchone()["c"],
            "unread": conn.execute("SELECT COUNT(*) AS c FROM messages WHERE is_read = 0").fetchone()["c"],
        }
        conn.close()
        return render_template("admin/dashboard.html", counts=counts)

    @app.route("/admin/settings", methods=["GET", "POST"])
    @login_required
    def admin_settings():
        conn = get_db()
        if request.method == "POST":
            keys = ["church_name", "tagline", "hero_verse", "hero_subtitle",
                    "welcome_heading", "welcome_body", "service_times", "address",
                    "contact_email", "contact_phone", "lineup_url", "footer_note",
                    "livestream_heading", "giving_heading", "giving_body", "giving_url",
                    "giving_button", "contact_heading", "contact_body"]
            for k in keys:
                conn.execute("UPDATE settings SET value = ? WHERE key = ?",
                             (request.form.get(k, "").strip(), k))
            conn.commit()
            conn.close()
            flash("Saved! Your homepage has been updated.", "success")
            return redirect(url_for("admin_settings"))
        s = get_settings(conn)
        conn.close()
        return render_template("admin/settings.html", s=s)

    @app.route("/admin/livestream", methods=["GET", "POST"])
    @login_required
    def admin_livestream():
        conn = get_db()
        if request.method == "POST":
            conn.execute("UPDATE settings SET value = ? WHERE key = 'livestream_url'",
                         (request.form.get("livestream_url", "").strip(),))
            conn.execute("UPDATE settings SET value = ? WHERE key = 'livestream_heading'",
                         (request.form.get("livestream_heading", "").strip(),))
            conn.commit()
            conn.close()
            flash("This week's live stream has been updated.", "success")
            return redirect(url_for("admin_livestream"))
        s = get_settings(conn)
        conn.close()
        return render_template("admin/livestream.html", s=s)

    # ---- Blog posts
    @app.route("/admin/posts")
    @login_required
    def admin_posts():
        conn = get_db()
        posts = conn.execute("SELECT * FROM posts ORDER BY created_at DESC").fetchall()
        conn.close()
        return render_template("admin/posts.html", posts=posts)

    @app.route("/admin/posts/new", methods=["GET", "POST"])
    @app.route("/admin/posts/<int:post_id>/edit", methods=["GET", "POST"])
    @login_required
    def admin_post_edit(post_id=None):
        conn = get_db()
        p = None
        if post_id:
            p = conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
            if p is None:
                conn.close(); abort(404)
        if request.method == "POST":
            title = request.form.get("title", "").strip()
            summary = request.form.get("summary", "").strip()
            body = request.form.get("body", "").strip()
            published = 1 if request.form.get("published") == "on" else 0
            if not title:
                conn.close(); flash("Please give your post a title.", "danger"); return redirect(request.url)
            try:
                new_media, _ = save_media(conn, request.files.get("image"), ALLOWED_IMAGE)
            except ValueError as e:
                conn.close(); flash(str(e), "danger"); return redirect(request.url)
            if post_id:
                slug = unique_slug(conn, title, post_id)
                if new_media:
                    delete_media(conn, p["image_media_id"])
                    conn.execute("UPDATE posts SET image_media_id = ? WHERE id = ?", (new_media, post_id))
                conn.execute("UPDATE posts SET title=?, slug=?, summary=?, body=?, published=? WHERE id=?",
                             (title, slug, summary, body, published, post_id))
                flash("Post updated.", "success")
            else:
                slug = unique_slug(conn, title)
                conn.execute(
                    "INSERT INTO posts (title, slug, summary, body, image_media_id, published, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (title, slug, summary, body, new_media, published, now_iso()))
                flash("Post published.", "success")
            conn.commit(); conn.close()
            return redirect(url_for("admin_posts"))
        conn.close()
        return render_template("admin/post_edit.html", p=p)

    @app.route("/admin/posts/<int:post_id>/delete", methods=["POST"])
    @login_required
    def admin_post_delete(post_id):
        conn = get_db()
        p = conn.execute("SELECT image_media_id FROM posts WHERE id = ?", (post_id,)).fetchone()
        conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))
        if p:
            delete_media(conn, p["image_media_id"])
        conn.commit(); conn.close()
        flash("Post deleted.", "info")
        return redirect(url_for("admin_posts"))

    # ---- Gallery
    @app.route("/admin/gallery", methods=["GET", "POST"])
    @login_required
    def admin_gallery():
        conn = get_db()
        if request.method == "POST":
            try:
                mid, _ = save_media(conn, request.files.get("image"), ALLOWED_IMAGE)
            except ValueError as e:
                conn.close(); flash(str(e), "danger"); return redirect(url_for("admin_gallery"))
            if mid:
                conn.execute("INSERT INTO gallery (media_id, caption, created_at) VALUES (?, ?, ?)",
                             (mid, request.form.get("caption", "").strip(), now_iso()))
                conn.commit()
                flash("Photo added to the gallery.", "success")
            else:
                flash("Please choose an image to upload.", "warning")
            conn.close()
            return redirect(url_for("admin_gallery"))
        items = conn.execute("SELECT * FROM gallery ORDER BY created_at DESC").fetchall()
        conn.close()
        return render_template("admin/gallery.html", items=items)

    @app.route("/admin/gallery/<int:item_id>/delete", methods=["POST"])
    @login_required
    def admin_gallery_delete(item_id):
        conn = get_db()
        row = conn.execute("SELECT media_id FROM gallery WHERE id = ?", (item_id,)).fetchone()
        conn.execute("DELETE FROM gallery WHERE id = ?", (item_id,))
        if row:
            delete_media(conn, row["media_id"])
        conn.commit(); conn.close()
        flash("Photo removed.", "info")
        return redirect(url_for("admin_gallery"))

    # ---- Presentations / sermons
    @app.route("/admin/presentations", methods=["GET", "POST"])
    @login_required
    def admin_presentations():
        conn = get_db()
        if request.method == "POST":
            title = request.form.get("title", "").strip()
            description = request.form.get("description", "").strip()
            link = request.form.get("url", "").strip()
            if not title:
                conn.close(); flash("Please give the presentation a title.", "danger")
                return redirect(url_for("admin_presentations"))
            try:
                mid, orig = save_media(conn, request.files.get("file"), ALLOWED_DOC)
            except ValueError as e:
                conn.close(); flash(str(e), "danger"); return redirect(url_for("admin_presentations"))
            conn.execute(
                "INSERT INTO presentations (title, description, url, file_media_id, file_name, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (title, description, link, mid, orig, now_iso()))
            conn.commit(); conn.close()
            flash("Presentation added.", "success")
            return redirect(url_for("admin_presentations"))
        items = conn.execute("SELECT * FROM presentations ORDER BY created_at DESC").fetchall()
        conn.close()
        return render_template("admin/presentations.html", items=items)

    @app.route("/admin/presentations/<int:item_id>/delete", methods=["POST"])
    @login_required
    def admin_presentation_delete(item_id):
        conn = get_db()
        row = conn.execute("SELECT file_media_id FROM presentations WHERE id = ?", (item_id,)).fetchone()
        conn.execute("DELETE FROM presentations WHERE id = ?", (item_id,))
        if row:
            delete_media(conn, row["file_media_id"])
        conn.commit(); conn.close()
        flash("Presentation removed.", "info")
        return redirect(url_for("admin_presentations"))

    # ---- Events
    @app.route("/admin/events")
    @login_required
    def admin_events():
        conn = get_db()
        items = conn.execute("SELECT * FROM events ORDER BY event_date, event_time").fetchall()
        conn.close()
        return render_template("admin/events.html", items=items)

    @app.route("/admin/events/new", methods=["GET", "POST"])
    @app.route("/admin/events/<int:event_id>/edit", methods=["GET", "POST"])
    @login_required
    def admin_event_edit(event_id=None):
        conn = get_db()
        ev = None
        if event_id:
            ev = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
            if ev is None:
                conn.close(); abort(404)
        if request.method == "POST":
            title = request.form.get("title", "").strip()
            description = request.form.get("description", "").strip()
            event_date = request.form.get("event_date", "").strip()
            event_time = request.form.get("event_time", "").strip()
            location = request.form.get("location", "").strip()
            if not title or not event_date:
                conn.close(); flash("Please add a title and a date.", "danger"); return redirect(request.url)
            if event_id:
                conn.execute("UPDATE events SET title=?, description=?, event_date=?, event_time=?, location=? WHERE id=?",
                             (title, description, event_date, event_time, location, event_id))
                flash("Event updated.", "success")
            else:
                conn.execute("INSERT INTO events (title, description, event_date, event_time, location, created_at)"
                             " VALUES (?, ?, ?, ?, ?, ?)",
                             (title, description, event_date, event_time, location, now_iso()))
                flash("Event added.", "success")
            conn.commit(); conn.close()
            return redirect(url_for("admin_events"))
        conn.close()
        return render_template("admin/event_edit.html", ev=ev)

    @app.route("/admin/events/<int:event_id>/delete", methods=["POST"])
    @login_required
    def admin_event_delete(event_id):
        conn = get_db()
        conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
        conn.commit(); conn.close()
        flash("Event removed.", "info")
        return redirect(url_for("admin_events"))

    # ---- Messages inbox
    @app.route("/admin/messages")
    @login_required
    def admin_messages():
        conn = get_db()
        items = conn.execute("SELECT * FROM messages ORDER BY created_at DESC").fetchall()
        conn.execute("UPDATE messages SET is_read = 1 WHERE is_read = 0")
        conn.commit(); conn.close()
        return render_template("admin/messages.html", items=items)

    @app.route("/admin/messages/<int:msg_id>/delete", methods=["POST"])
    @login_required
    def admin_message_delete(msg_id):
        conn = get_db()
        conn.execute("DELETE FROM messages WHERE id = ?", (msg_id,))
        conn.commit(); conn.close()
        flash("Message deleted.", "info")
        return redirect(url_for("admin_messages"))

    # ---- Change password
    @app.route("/admin/password", methods=["GET", "POST"])
    @login_required
    def admin_password():
        conn = get_db()
        if request.method == "POST":
            current = request.form.get("current", "")
            new = request.form.get("new", "")
            confirm = request.form.get("confirm", "")
            u = conn.execute("SELECT * FROM users WHERE username = ?", (session["admin"],)).fetchone()
            if not check_password_hash(u["password_hash"], current):
                flash("Your current password is incorrect.", "danger")
            elif len(new) < 6 or new != confirm:
                flash("New password must be 6+ characters and match.", "danger")
            else:
                conn.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                             (generate_password_hash(new, method="pbkdf2:sha256"), u["id"]))
                conn.commit()
                flash("Password changed.", "success")
            conn.close()
            return redirect(url_for("admin_password"))
        conn.close()
        return render_template("admin/password.html")

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=bool(os.environ.get("FLASK_DEBUG")))
