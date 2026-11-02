"""
⚠️ Intentionally vulnerable practice labs.

Each lab is vulnerable on purpose for learning, but isolated so it can't harm the real server.
- SQLi: uses a fresh in-memory SQLite per request (unrelated to the platform DB); no stacked queries
- Path traversal: reads only from a virtual filesystem (dict), never the real disk
- Cookie tampering: a separate cookie, unrelated to the platform login session
"""
import base64
import binascii
import json
import posixpath
import secrets
import sqlite3

from flask import Blueprint, Response, abort, make_response, render_template, request

from .models import Challenge

bp = Blueprint("labs", __name__, url_prefix="/labs")


def flag_for(key):
    chal = Challenge.query.filter_by(lab_key=key).first()
    if chal is None or not chal.visible:
        abort(404)
    return chal.flag


# ---------- 1. Invisible Note (HTML comment) ----------

@bp.route("/hidden")
def hidden():
    return render_template("labs/hidden.html", flag=flag_for("hidden"))


# ---------- 2. No Robots Allowed (robots.txt) ----------

@bp.route("/robots/")
def robots_index():
    flag_for("robots")
    return render_template("labs/robots.html")


@bp.route("/robots/robots.txt")
def robots_txt():
    flag_for("robots")
    body = (
        "User-agent: *\n"
        "Disallow: /labs/robots/s3cr3t-4dm1n-p4n3l\n"
    )
    return Response(body, mimetype="text/plain")


@bp.route("/robots/s3cr3t-4dm1n-p4n3l")
def robots_secret():
    return render_template("labs/robots_secret.html", flag=flag_for("robots"))


# ---------- 3. Cookie Monster (unsigned cookie tampering) ----------

COOKIE_NAME = "lab_profile"


@bp.route("/cookie")
def cookie():
    flag = flag_for("cookie")
    raw = request.cookies.get(COOKIE_NAME)
    profile, error = None, None
    if raw:
        try:
            profile = json.loads(base64.b64decode(raw, validate=False).decode())
            if not isinstance(profile, dict):
                raise ValueError
        except (binascii.Error, ValueError, UnicodeDecodeError):
            error = "Could not parse the cookie. (It should be base64-encoded JSON.)"
            profile = None

    set_default = profile is None and error is None
    if set_default:
        profile = {"user": "guest", "role": "guest"}

    is_admin = profile is not None and profile.get("role") == "admin"
    resp = make_response(render_template(
        "labs/cookie.html", profile=profile, is_admin=is_admin, flag=flag, error=error,
    ))
    if set_default:
        value = base64.b64encode(json.dumps(profile).encode()).decode()
        resp.set_cookie(COOKIE_NAME, value, path="/labs/cookie", samesite="Lax")
    return resp


# ---------- 4. Someone Else's Notes (IDOR) ----------

def _notes():
    return {
        1: ("admin", "admin notes", f"don't forget: {flag_for('idor')}"),
        2: ("alice", "groceries", "milk, eggs, apples"),
        3: ("guest", "my note", "todo: play the wargame!\n(nobody else can read my notes... right?)"),
        4: ("bob", "password hint", "dog's name + birthday... probably shouldn't write that here"),
        5: ("alice", "trip plan", "4 days on Jeju island"),
    }


@bp.route("/idor/")
def idor_index():
    flag_for("idor")
    return render_template("labs/idor.html", note=None, note_id=3, mine=[3])


@bp.route("/idor/notes/<int:note_id>")
def idor_note(note_id):
    notes = _notes()
    if note_id not in notes:
        abort(404)
    owner, title, body = notes[note_id]
    # Vulnerability: never checks that the logged-in user (guest) owns the note
    return render_template(
        "labs/idor.html", note={"owner": owner, "title": title, "body": body},
        note_id=note_id, mine=[3],
    )


# ---------- 5. SQL Login (SQL injection) ----------

def _fresh_db():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, password TEXT)")
    conn.executemany(
        "INSERT INTO users (username, password) VALUES (?, ?)",
        [("admin", secrets.token_hex(16)), ("guest", "guest")],
    )
    return conn


@bp.route("/sqli", methods=["GET", "POST"])
def sqli():
    flag = flag_for("sqli")
    ctx = {"query": None, "result": None, "error": None, "flag": None, "username": ""}
    if request.method == "POST":
        username = request.form.get("username", "")[:200]
        password = request.form.get("password", "")[:200]
        ctx["username"] = username
        # Vulnerability: user input is concatenated straight into the query
        query = (
            "SELECT username FROM users "
            f"WHERE username = '{username}' AND password = '{password}'"
        )
        ctx["query"] = query
        conn = _fresh_db()
        try:
            row = conn.execute(query).fetchone()  # execute() runs a single statement only
        except (sqlite3.Error, sqlite3.Warning) as e:
            ctx["error"] = str(e)
            row = None
        finally:
            conn.close()

        if row:
            ctx["result"] = row[0]
            if row[0] == "admin":
                ctx["flag"] = flag
        elif not ctx["error"]:
            ctx["error"] = "Login failed"
    return render_template("labs/sqli.html", **ctx)


# ---------- 6. File Viewer (path traversal, virtual filesystem) ----------

BASE_DIR = "/srv/files"


def _vfs():
    return {
        "/srv/files/welcome.txt": "Welcome to the file viewer!\npublic files: welcome.txt, notice.txt",
        "/srv/files/notice.txt": "[notice] security update: ../ is now filtered. You're safe :)",
        "/srv/secret/flag.txt": flag_for("traversal"),
        "/etc/passwd": "root:x:0:0:root:/root:/bin/bash\nwww-data:x:33:33::/var/www:/usr/sbin/nologin",
        "/etc/hostname": "usg-lab",
    }


@bp.route("/files")
def files():
    vfs = _vfs()
    name = request.args.get("name", "welcome.txt")[:200]
    # Vulnerability: strips '../' only once, so input like '....//' gets through
    filtered = name.replace("../", "")
    if filtered.startswith("/"):
        return render_template(
            "labs/files.html", name=name, filtered=filtered, path=None, content=None,
            blocked="Absolute paths are not allowed.",
        )
    path = posixpath.normpath(posixpath.join(BASE_DIR, filtered))
    content = vfs.get(path)
    return render_template(
        "labs/files.html", name=name, filtered=filtered, path=path, content=content,
        blocked=None,
    )
