import re
from urllib.parse import urlsplit

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from .extensions import db
from .models import User

bp = Blueprint("auth", __name__)

USERNAME_RE = re.compile(r"^[A-Za-z0-9_\-]{3,20}$")


def _safe_next(target):
    """오픈 리다이렉트 방지: 같은 사이트의 상대 경로만 허용."""
    if not target:
        return None
    parts = urlsplit(target)
    if parts.scheme or parts.netloc or not target.startswith("/") or target.startswith("//"):
        return None
    if "\\" in target:
        return None
    return target


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.challenges"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")

        error = None
        if not USERNAME_RE.match(username):
            error = "아이디는 3~20자의 영문, 숫자, _, - 만 사용할 수 있습니다."
        elif len(password) < 8:
            error = "비밀번호는 8자 이상이어야 합니다."
        elif password != confirm:
            error = "비밀번호 확인이 일치하지 않습니다."
        elif User.query.filter(db.func.lower(User.username) == username.lower()).first():
            error = "이미 사용 중인 아이디입니다."

        if error:
            flash(error, "error")
            return render_template("auth/register.html", username=username), 400

        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        flash(f"환영합니다, {username}! 첫 문제부터 시작해 보세요 🚩", "success")
        return redirect(url_for("main.challenges"))

    return render_template("auth/register.html", username="")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.challenges"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if user is None or not user.check_password(password):
            flash("아이디 또는 비밀번호가 올바르지 않습니다.", "error")
            return render_template("auth/login.html", username=username), 401

        login_user(user, remember=bool(request.form.get("remember")))
        flash("로그인했습니다.", "success")
        return redirect(_safe_next(request.args.get("next")) or url_for("main.challenges"))

    return render_template("auth/login.html", username="")


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("로그아웃했습니다.", "info")
    return redirect(url_for("main.index"))
