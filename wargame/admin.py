from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from .extensions import db
from .models import Challenge, Solve, Submission, User

bp = Blueprint("admin", __name__, url_prefix="/admin")

CATEGORIES = ["misc", "web", "crypto", "forensics", "reversing", "pwn"]
DIFFICULTIES = ["easy", "medium", "hard"]


@bp.before_request
@login_required
def require_admin():
    if not current_user.is_admin:
        abort(403)


@bp.route("/")
def dashboard():
    stats = {
        "users": User.query.count(),
        "challenges": Challenge.query.count(),
        "solves": Solve.query.count(),
        "submissions": Submission.query.count(),
        "wrong": Submission.query.filter_by(correct=False).count(),
    }
    recent = Submission.query.order_by(Submission.created_at.desc()).limit(10).all()
    return render_template("admin/dashboard.html", stats=stats, recent=recent)


# ---------- 문제 관리 ----------

@bp.route("/challenges")
def challenges():
    chals = Challenge.query.order_by(Challenge.category, Challenge.points).all()
    return render_template("admin/challenges.html", chals=chals)


def _fill_challenge(chal, form):
    errors = []
    title = form.get("title", "").strip()
    category = form.get("category", "").strip().lower()
    difficulty = form.get("difficulty", "easy")
    flag = form.get("flag", "").strip()
    url = form.get("url", "").strip()
    try:
        points = int(form.get("points", "0"))
    except ValueError:
        points = -1

    if not title or len(title) > 100:
        errors.append("제목은 1~100자여야 합니다.")
    if not category or len(category) > 32:
        errors.append("카테고리를 입력하세요.")
    if difficulty not in DIFFICULTIES:
        errors.append("난이도가 올바르지 않습니다.")
    if not (0 <= points <= 10000):
        errors.append("점수는 0~10000 사이 정수여야 합니다.")
    if not flag or len(flag) > 256:
        errors.append("플래그는 1~256자여야 합니다.")
    if url and not (url.startswith("/") or url.startswith("http://") or url.startswith("https://")):
        errors.append("URL은 / 또는 http(s):// 로 시작해야 합니다.")

    chal.title = title
    chal.category = category
    chal.difficulty = difficulty
    chal.points = max(points, 0)
    chal.flag = flag
    chal.url = url or None
    chal.description = form.get("description", "")
    chal.visible = bool(form.get("visible"))
    return errors


@bp.route("/challenges/new", methods=["GET", "POST"])
def challenge_new():
    chal = Challenge(visible=True, points=100, category="web", difficulty="easy", flag="")
    if request.method == "POST":
        errors = _fill_challenge(chal, request.form)
        if errors:
            for e in errors:
                flash(e, "error")
        else:
            db.session.add(chal)
            db.session.commit()
            flash("문제를 만들었습니다.", "success")
            return redirect(url_for("admin.challenges"))
    return render_template(
        "admin/challenge_form.html", chal=chal, is_new=True,
        categories=CATEGORIES, difficulties=DIFFICULTIES,
    )


@bp.route("/challenges/<int:chal_id>/edit", methods=["GET", "POST"])
def challenge_edit(chal_id):
    chal = db.get_or_404(Challenge, chal_id)
    if request.method == "POST":
        errors = _fill_challenge(chal, request.form)
        if errors:
            db.session.rollback()
            for e in errors:
                flash(e, "error")
            chal = db.get_or_404(Challenge, chal_id)
        else:
            db.session.commit()
            flash("저장했습니다.", "success")
            return redirect(url_for("admin.challenges"))
    return render_template(
        "admin/challenge_form.html", chal=chal, is_new=False,
        categories=CATEGORIES, difficulties=DIFFICULTIES,
    )


@bp.route("/challenges/<int:chal_id>/toggle", methods=["POST"])
def challenge_toggle(chal_id):
    chal = db.get_or_404(Challenge, chal_id)
    chal.visible = not chal.visible
    db.session.commit()
    flash(f"'{chal.title}' {'공개' if chal.visible else '비공개'}로 변경", "info")
    return redirect(url_for("admin.challenges"))


@bp.route("/challenges/<int:chal_id>/delete", methods=["POST"])
def challenge_delete(chal_id):
    chal = db.get_or_404(Challenge, chal_id)
    if chal.lab_key:
        flash("내장 실습 문제는 삭제 대신 비공개로 전환하세요.", "error")
        return redirect(url_for("admin.challenges"))
    db.session.delete(chal)
    db.session.commit()
    flash("문제를 삭제했습니다.", "success")
    return redirect(url_for("admin.challenges"))


# ---------- 유저 관리 ----------

@bp.route("/users")
def users():
    all_users = User.query.order_by(User.created_at.desc()).all()
    return render_template("admin/users.html", users=all_users)


def _target_user(user_id):
    u = db.get_or_404(User, user_id)
    if u.id == current_user.id:
        flash("자기 자신에게는 할 수 없습니다.", "error")
        return None
    return u


@bp.route("/users/<int:user_id>/toggle-admin", methods=["POST"])
def user_toggle_admin(user_id):
    u = _target_user(user_id)
    if u:
        u.is_admin = not u.is_admin
        db.session.commit()
        flash(f"{u.username}: 관리자 권한 {'부여' if u.is_admin else '해제'}", "info")
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:user_id>/toggle-hidden", methods=["POST"])
def user_toggle_hidden(user_id):
    u = db.get_or_404(User, user_id)
    u.hidden = not u.hidden
    db.session.commit()
    flash(f"{u.username}: 스코어보드 {'숨김' if u.hidden else '표시'}", "info")
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:user_id>/delete", methods=["POST"])
def user_delete(user_id):
    u = _target_user(user_id)
    if u:
        db.session.delete(u)
        db.session.commit()
        flash(f"{u.username} 계정을 삭제했습니다.", "success")
    return redirect(url_for("admin.users"))


# ---------- 제출 로그 ----------

@bp.route("/submissions")
def submissions():
    only = request.args.get("only")
    q = Submission.query
    if only == "correct":
        q = q.filter_by(correct=True)
    elif only == "wrong":
        q = q.filter_by(correct=False)
    subs = q.order_by(Submission.created_at.desc()).limit(300).all()
    return render_template("admin/submissions.html", subs=subs, only=only)
