from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from .extensions import db
from .models import Challenge, Solve, Submission, User

bp = Blueprint("admin", __name__, url_prefix="/admin")

CATEGORIES = ["misc", "web", "crypto", "cloud", "k-osint", "forensics", "reversing", "pwn"]
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


# ---------- challenges ----------

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
    author = form.get("author", "").strip()
    try:
        points = int(form.get("points", "0"))
    except ValueError:
        points = -1

    if not title or len(title) > 100:
        errors.append("Title must be 1–100 characters.")
    if not category or len(category) > 32:
        errors.append("Category is required.")
    if difficulty not in DIFFICULTIES:
        errors.append("Invalid difficulty.")
    if not (0 <= points <= 10000):
        errors.append("Points must be an integer from 0 to 10000.")
    if not flag or len(flag) > 256:
        errors.append("Flag must be 1–256 characters.")
    if url and not (url.startswith("/") or url.startswith("http://") or url.startswith("https://")):
        errors.append("URL must start with / or http(s)://.")
    if len(author) > 64:
        errors.append("Author must be at most 64 characters.")

    chal.title = title
    chal.category = category
    chal.difficulty = difficulty
    chal.points = max(points, 0)
    chal.flag = flag
    chal.url = url or None
    chal.author = author or None
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
            flash("Challenge created.", "success")
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
            flash("Saved.", "success")
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
    flash(f"'{chal.title}' is now {'visible' if chal.visible else 'hidden'}.", "info")
    return redirect(url_for("admin.challenges"))


@bp.route("/challenges/<int:chal_id>/delete", methods=["POST"])
def challenge_delete(chal_id):
    chal = db.get_or_404(Challenge, chal_id)
    if chal.lab_key:
        flash("Built-in lab challenges can't be deleted — hide them instead.", "error")
        return redirect(url_for("admin.challenges"))
    db.session.delete(chal)
    db.session.commit()
    flash("Challenge deleted.", "success")
    return redirect(url_for("admin.challenges"))


# ---------- users ----------

@bp.route("/users")
def users():
    all_users = User.query.order_by(User.created_at.desc()).all()
    return render_template("admin/users.html", users=all_users)


def _target_user(user_id):
    u = db.get_or_404(User, user_id)
    if u.id == current_user.id:
        flash("You can't do that to yourself.", "error")
        return None
    return u


@bp.route("/users/<int:user_id>/toggle-admin", methods=["POST"])
def user_toggle_admin(user_id):
    u = _target_user(user_id)
    if u:
        u.is_admin = not u.is_admin
        db.session.commit()
        flash(f"{u.username}: admin {'granted' if u.is_admin else 'revoked'}.", "info")
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:user_id>/toggle-hidden", methods=["POST"])
def user_toggle_hidden(user_id):
    u = db.get_or_404(User, user_id)
    u.hidden = not u.hidden
    db.session.commit()
    flash(f"{u.username}: {'hidden from' if u.hidden else 'shown on'} the scoreboard.", "info")
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:user_id>/delete", methods=["POST"])
def user_delete(user_id):
    u = _target_user(user_id)
    if u:
        db.session.delete(u)
        db.session.commit()
        flash(f"Deleted account {u.username}.", "success")
    return redirect(url_for("admin.users"))


# ---------- submission log ----------

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
