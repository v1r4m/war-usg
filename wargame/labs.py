"""
⚠️ Intentionally vulnerable practice labs.

Each lab is vulnerable on purpose for learning, but isolated so it can't harm the real server.
- SQLi: uses a fresh in-memory SQLite per request (unrelated to the platform DB); no stacked queries
- Path traversal: reads only from a virtual filesystem (dict), never the real disk
- Cookie tampering: a separate cookie, unrelated to the platform login session
- S3 versioning: an in-memory imitation of an S3 bucket (dict), no AWS account involved
"""
import base64
import binascii
import hashlib
import html
import json
import posixpath
import secrets
import sqlite3
from xml.sax.saxutils import escape as xml_escape

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


# ---------- 7. Deleted, Not Gone (S3 versioning, in-memory bucket) ----------

S3_BUCKET = "ocean-corp-portal"
S3_REGION = "ap-northeast-2"
S3_REST = f"/labs/s3/{S3_BUCKET}"
S3_WEB = "/labs/s3web"

_S3_STYLE = (
    "body{font-family:Arial,sans-serif;margin:0;background:#f4f5f7;color:#222}"
    "header{background:#0b3d91;color:#fff;padding:16px 24px}header a{color:#cfe0ff}"
    "main{max-width:760px;margin:24px auto;background:#fff;padding:24px;border-radius:6px}"
    "h1{margin:0;font-size:20px}nav{color:#cfe0ff;font-size:13px;margin-top:6px}"
    "pre{background:#f4f5f7;padding:12px;white-space:pre-wrap;word-break:break-all}"
)


def _s3_page(title, body):
    # The stylesheet is pulled straight from the bucket's REST endpoint, which leaks the bucket name.
    return (
        f"<!doctype html><html><head><meta charset='utf-8'><title>{title}</title>"
        f"<link rel='stylesheet' href='{S3_REST}/assets/style.css'></head><body>"
        f"<header><h1>Ocean Corp Employee Portal</h1>"
        f"<nav>Home · Notices · Directory · Benefits · IT Helpdesk · <a href='/challenges'>← wargame</a></nav></header>"
        f"<main>{body}</main></body></html>"
    )


def _s3_objects():
    """key -> versions, oldest first. Each version is (last_modified, body) or (last_modified, None) for a delete marker."""
    flag = flag_for("s3versions")
    report = _s3_page("Security Incident Postmortem - 2026-08", (
        "<h2>Security incident postmortem (2026-08)</h2>"
        "<p>In early August an access key was accidentally printed to the deploy pipeline logs.</p>"
        "<p>The key was rotated immediately. The original value is kept below for tracking:</p>"
        f"<pre>{flag}</pre>"
        "<p>Access to this document was restricted after internal review.</p>"
    ))
    return {
        "index.html": [("2026-08-01T09:00:00.000Z", _s3_page("Ocean Corp Portal", (
            "<p>Hello, everyone.</p><p>Check the menu above for the latest notices and internal resources.</p>"
            "<p style='color:#888;font-size:13px'>Now served from S3 static website hosting. "
            "Cheaper, faster, and the security team says it's locked down. 🔒</p>"
        )))],
        "robots.txt": [("2026-08-01T09:00:00.000Z", f"User-agent: *\nDisallow: {S3_WEB}/confidential/\n")],
        "assets/style.css": [("2026-08-01T09:00:00.000Z", _S3_STYLE)],
        "confidential/index.html": [("2026-08-01T09:05:00.000Z", _s3_page("Employee Resources", (
            "<h2>Employees only</h2><ul>"
            "<li><a href='it-security-incident-2026-08.html'>2026-08 security incident postmortem</a> (restricted after review)</li>"
            "<li><a href='q3-payroll-notes.html'>Q3 payroll notes</a></li>"
            "<li><a href='vpn-config-backup.html'>VPN config backup</a></li></ul>"
        )))],
        "confidential/q3-payroll-notes.html": [
            ("2026-08-20T02:10:00.000Z", _s3_page("Q3 Payroll Notes", "<p>Q3 payday has moved to 9/25.</p>")),
            ("2026-08-21T05:42:00.000Z", _s3_page("Q3 Payroll Notes", "<p>Q3 payday has moved to 9/25. (edit: added per-team notes)</p>")),
        ],
        "confidential/vpn-config-backup.html": [
            ("2026-08-22T01:00:00.000Z", _s3_page("VPN Config Backup", "<p>Ask the IT helpdesk for the VPN backup procedure.</p>")),
        ],
        "confidential/it-security-incident-2026-08.html": [
            ("2026-08-25T07:31:00.000Z", report),
            ("2026-08-25T07:48:00.000Z", None),
        ],
    }


def _s3_version_id(key, idx):
    raw = hashlib.sha256(f"{flag_for('s3versions')}:{key}:{idx}".encode()).digest()
    return base64.urlsafe_b64encode(raw).decode()[:32].replace("-", "x").replace("_", "y")


def _s3_mime(key):
    if key.endswith(".css"):
        return "text/css"
    if key.endswith(".txt"):
        return "text/plain; charset=utf-8"
    return "text/html; charset=utf-8"


def _s3_response(body, status=200, mimetype="application/xml", headers=None):
    resp = Response(body, status=status, mimetype=mimetype)
    resp.headers["Server"] = "AmazonS3"
    resp.headers["x-amz-request-id"] = secrets.token_hex(8).upper()
    resp.headers["x-amz-bucket-region"] = S3_REGION
    for k, v in (headers or {}).items():
        resp.headers[k] = v
    return resp


def _s3_error(code, message, status, extra="", headers=None):
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f"<Error><Code>{code}</Code><Message>{message}</Message>{extra}"
        f"<RequestId>{secrets.token_hex(8).upper()}</RequestId></Error>"
    )
    return _s3_response(body, status=status, headers=headers)


def _s3_list_versions(prefix):
    entries = []
    for key, versions in sorted(_s3_objects().items()):
        if not key.startswith(prefix):
            continue
        last = len(versions) - 1
        for idx in range(last, -1, -1):
            modified, body = versions[idx]
            common = (
                f"<Key>{xml_escape(key)}</Key><VersionId>{_s3_version_id(key, idx)}</VersionId>"
                f"<IsLatest>{'true' if idx == last else 'false'}</IsLatest>"
                f"<LastModified>{modified}</LastModified>"
            )
            if body is None:
                entries.append(f"<DeleteMarker>{common}</DeleteMarker>")
            else:
                etag = hashlib.md5(body.encode()).hexdigest()
                entries.append(
                    f"<Version>{common}<ETag>&quot;{etag}&quot;</ETag>"
                    f"<Size>{len(body.encode())}</Size><StorageClass>STANDARD</StorageClass></Version>"
                )
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<ListVersionsResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
        f"<Name>{S3_BUCKET}</Name><Prefix>{xml_escape(prefix)}</Prefix><KeyMarker></KeyMarker>"
        f"<VersionIdMarker></VersionIdMarker><MaxKeys>1000</MaxKeys><IsTruncated>false</IsTruncated>"
        + "".join(entries) + "</ListVersionsResult>"
    )
    return _s3_response(body)


@bp.route("/s3/<bucket>/", defaults={"key": ""}, methods=["GET", "HEAD"])
@bp.route("/s3/<bucket>/<path:key>", methods=["GET", "HEAD"])
def s3_rest(bucket, key):
    """REST endpoint. The bucket policy allows s3:Get* on objects and s3:ListBucketVersions, but not s3:ListBucket."""
    flag_for("s3versions")
    if bucket != S3_BUCKET:
        return _s3_error("NoSuchBucket", "The specified bucket does not exist", 404,
                         f"<BucketName>{xml_escape(bucket[:100])}</BucketName>")

    if not key:
        if "versions" in request.args:
            return _s3_list_versions(request.args.get("prefix", "")[:200])
        # ListObjects / ListObjectsV2 / ?policy / ?acl ... are all outside the policy
        return _s3_error("AccessDenied", "Access Denied", 403)

    versions = _s3_objects().get(key)
    if versions is None:
        return _s3_error("NoSuchKey", "The specified key does not exist.", 404,
                         f"<Key>{xml_escape(key[:200])}</Key>")

    version_id = request.args.get("versionId")
    if version_id is None:
        idx = len(versions) - 1
    else:
        idx = next((i for i in range(len(versions)) if _s3_version_id(key, i) == version_id), None)
        if idx is None:
            return _s3_error("NoSuchVersion", "The specified version does not exist.", 404,
                             f"<Key>{xml_escape(key)}</Key><VersionId>{xml_escape(version_id[:100])}</VersionId>")

    body = versions[idx][1]
    vid = _s3_version_id(key, idx)
    if body is None:
        if version_id is None:
            # GET on a key whose latest version is a delete marker
            return _s3_error("NoSuchKey", "The specified key does not exist.", 404,
                             f"<Key>{xml_escape(key)}</Key>",
                             headers={"x-amz-delete-marker": "true", "x-amz-version-id": vid})
        return _s3_error("MethodNotAllowed", "The specified method is not allowed against this resource.", 405)

    return _s3_response(body, mimetype=_s3_mime(key), headers={
        "x-amz-version-id": vid,
        "ETag": f'"{hashlib.md5(body.encode()).hexdigest()}"',
    })


@bp.route("/s3web/", defaults={"key": ""})
@bp.route("/s3web/<path:key>")
def s3_website(key):
    """Static website endpoint: index documents for folders, no versionId, no listings."""
    flag_for("s3versions")
    if key == "" or key.endswith("/"):
        key += "index.html"
    versions = _s3_objects().get(key)
    if versions is None or versions[-1][1] is None:
        safe_key = html.escape(key)
        body = (
            "<html><head><title>404 Not Found</title></head><body><h1>404 Not Found</h1><ul>"
            "<li>Code: NoSuchKey</li><li>Message: The specified key does not exist.</li>"
            f"<li>Key: {safe_key}</li><li>RequestId: {secrets.token_hex(8).upper()}</li></ul><hr/></body></html>"
        )
        return _s3_response(body, status=404, mimetype="text/html")
    return _s3_response(versions[-1][1], mimetype=_s3_mime(key))
