from collections import OrderedDict
from datetime import timedelta

from flask import (
    Blueprint, abort, current_app, flash, redirect, render_template, request, url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from .extensions import db
from .models import Challenge, Solve, Submission, User, scoreboard, utcnow

bp = Blueprint("main", __name__)

CATEGORY_ORDER = ["misc", "web", "crypto", "forensics", "reversing", "pwn"]
DIFFICULTY_ORDER = {"easy": 0, "medium": 1, "hard": 2}


def _visible_challenges():
    q = Challenge.query
    if not (current_user.is_authenticated and current_user.is_admin):
        q = q.filter_by(visible=True)
    return q


def _solve_counts():
    rows = (
        db.session.query(Solve.challenge_id, func.count(Solve.id))
        .join(User, User.id == Solve.user_id)
        .filter(User.is_admin.is_(False), User.hidden.is_(False))
        .group_by(Solve.challenge_id)
        .all()
    )
    return dict(rows)


@bp.route("/")
def index():
    recent = (
        Solve.query.join(User).join(Challenge)
        .filter(User.is_admin.is_(False), User.hidden.is_(False), Challenge.visible.is_(True))
        .order_by(Solve.solved_at.desc())
        .limit(8)
        .all()
    )
    stats = {
        "challenges": Challenge.query.filter_by(visible=True).count(),
        "users": User.query.filter_by(is_admin=False, hidden=False).count(),
        "solves": Solve.query.count(),
    }
    return render_template("index.html", recent=recent, stats=stats, top=scoreboard(limit=5))


@bp.route("/challenges")
@login_required
def challenges():
    chals = _visible_challenges().all()
    chals.sort(key=lambda c: (DIFFICULTY_ORDER.get(c.difficulty, 9), c.points, c.id))

    grouped = OrderedDict()
    cats = sorted(
        {c.category for c in chals},
        key=lambda c: (CATEGORY_ORDER.index(c) if c in CATEGORY_ORDER else 99, c),
    )
    for cat in cats:
        grouped[cat] = [c for c in chals if c.category == cat]

    solved_ids = {s.challenge_id for s in current_user.solves}
    return render_template(
        "challenges/list.html",
        grouped=grouped,
        solved_ids=solved_ids,
        counts=_solve_counts(),
        total=len(chals),
    )


@bp.route("/challenges/<int:chal_id>", methods=["GET", "POST"])
@login_required
def challenge(chal_id):
    chal = _visible_challenges().filter_by(id=chal_id).first()
    if chal is None:
        abort(404)

    solved = current_user.has_solved(chal.id)

    if request.method == "POST":
        if solved:
            flash("이미 해결한 문제입니다.", "info")
            return redirect(url_for("main.challenge", chal_id=chal.id))

        limit = current_app.config["SUBMIT_RATE_LIMIT"]
        recent = Submission.query.filter(
            Submission.user_id == current_user.id,
            Submission.created_at >= utcnow() - timedelta(minutes=1),
        ).count()
        if recent >= limit:
            flash("제출이 너무 잦습니다. 1분 뒤에 다시 시도하세요.", "error")
            return redirect(url_for("main.challenge", chal_id=chal.id))

        submitted = request.form.get("flag", "").strip()[:256]
        if not submitted:
            flash("플래그를 입력하세요.", "error")
            return redirect(url_for("main.challenge", chal_id=chal.id))

        correct = chal.check_flag(submitted)
        db.session.add(Submission(
            user_id=current_user.id, challenge_id=chal.id, content=submitted,
            correct=correct, ip=request.remote_addr,
        ))

        if correct:
            first_blood = not any(
                not s.user.is_admin and not s.user.hidden for s in chal.solves
            )
            db.session.add(Solve(user_id=current_user.id, challenge_id=chal.id))
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash("이미 해결한 문제입니다.", "info")
                return redirect(url_for("main.challenge", chal_id=chal.id))
            if first_blood and not (current_user.is_admin or current_user.hidden):
                flash(f"🩸 퍼스트 블러드! +{chal.points}점", "success")
            else:
                flash(f"정답입니다! +{chal.points}점 🎉", "success")
        else:
            db.session.commit()
            flash("틀렸습니다. 다시 시도해 보세요.", "error")
        return redirect(url_for("main.challenge", chal_id=chal.id))

    solvers = [s for s in chal.solves if not s.user.is_admin and not s.user.hidden]
    return render_template("challenges/detail.html", chal=chal, solved=solved, solvers=solvers)


@bp.route("/scoreboard")
def scoreboard_page():
    return render_template("scoreboard.html", rows=scoreboard())


@bp.route("/users/<int:user_id>")
def user(user_id):
    u = db.session.get(User, user_id)
    if u is None or (u.hidden and not (current_user.is_authenticated and current_user.is_admin)):
        abort(404)
    solves = sorted(u.solves, key=lambda s: s.solved_at, reverse=True)
    rank = None
    for i, row in enumerate(scoreboard(), start=1):
        if row[0].id == u.id:
            rank = i
            break
    return render_template("user.html", u=u, solves=solves, rank=rank)
