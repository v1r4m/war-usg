"""
⚠️ 실습용 '일부러 취약한' 문제들.

각 실습은 학습을 위해 의도적으로 취약하게 만들었지만, 실제 서버에는 피해가 가지 않도록 격리되어 있습니다.
- SQLi: 요청마다 새로 만드는 인메모리 SQLite만 사용 (플랫폼 DB와 무관), 다중 쿼리 실행 불가
- 경로 탐색: 실제 디스크가 아닌 가상 파일시스템(dict)만 조회
- 쿠키 변조: 플랫폼 로그인 세션과 무관한 별도 쿠키
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


# ---------- 1. 보이지 않는 메모 (HTML 주석) ----------

@bp.route("/hidden")
def hidden():
    return render_template("labs/hidden.html", flag=flag_for("hidden"))


# ---------- 2. 로봇은 출입금지 (robots.txt) ----------

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


# ---------- 3. 쿠키 몬스터 (서명 없는 쿠키 변조) ----------

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
            error = "쿠키를 해석할 수 없습니다. (base64로 인코딩된 JSON이어야 해요)"
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


# ---------- 4. 남의 메모장 (IDOR) ----------

def _notes():
    return {
        1: ("admin", "관리자 메모", f"잊지 말 것: {flag_for('idor')}"),
        2: ("alice", "장보기", "우유, 계란, 사과"),
        3: ("guest", "내 메모", "오늘 할 일: 워게임 풀기!\n(다른 사람 메모는 볼 수 없겠지?)"),
        4: ("bob", "비밀번호 힌트", "강아지 이름 + 생일... 이라고 쓰면 안 되겠지"),
        5: ("alice", "여행 계획", "제주도 3박 4일"),
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
    # 취약점: 로그인한 사용자(guest)가 메모의 주인인지 확인하지 않음
    return render_template(
        "labs/idor.html", note={"owner": owner, "title": title, "body": body},
        note_id=note_id, mine=[3],
    )


# ---------- 5. SQL 로그인 (SQL Injection) ----------

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
        # 취약점: 사용자 입력을 그대로 문자열에 이어 붙임
        query = (
            "SELECT username FROM users "
            f"WHERE username = '{username}' AND password = '{password}'"
        )
        ctx["query"] = query
        conn = _fresh_db()
        try:
            row = conn.execute(query).fetchone()  # execute()는 쿼리 1개만 실행
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
            ctx["error"] = "로그인 실패"
    return render_template("labs/sqli.html", **ctx)


# ---------- 6. 파일 뷰어 (Path Traversal, 가상 파일시스템) ----------

BASE_DIR = "/srv/files"


def _vfs():
    return {
        "/srv/files/welcome.txt": "파일 뷰어에 오신 것을 환영합니다!\n공개 파일: welcome.txt, notice.txt",
        "/srv/files/notice.txt": "[공지] 보안 강화: 이제 ../ 는 필터링됩니다. 안심하세요 :)",
        "/srv/secret/flag.txt": flag_for("traversal"),
        "/etc/passwd": "root:x:0:0:root:/root:/bin/bash\nwww-data:x:33:33::/var/www:/usr/sbin/nologin",
        "/etc/hostname": "usg-lab",
    }


@bp.route("/files")
def files():
    vfs = _vfs()
    name = request.args.get("name", "welcome.txt")[:200]
    # 취약점: '../' 를 '한 번만' 지움 → '....//' 같은 입력으로 우회 가능
    filtered = name.replace("../", "")
    if filtered.startswith("/"):
        return render_template(
            "labs/files.html", name=name, filtered=filtered, path=None, content=None,
            blocked="절대 경로는 허용되지 않습니다.",
        )
    path = posixpath.normpath(posixpath.join(BASE_DIR, filtered))
    content = vfs.get(path)
    return render_template(
        "labs/files.html", name=name, filtered=filtered, path=path, content=content,
        blocked=None,
    )
