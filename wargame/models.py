import hmac
from datetime import datetime, timezone

from flask_login import UserMixin
from sqlalchemy import asc, desc, func
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(32), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    hidden = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    solves = db.relationship("Solve", back_populates="user", cascade="all, delete-orphan")
    submissions = db.relationship(
        "Submission", back_populates="user", cascade="all, delete-orphan"
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def score(self):
        return sum(s.challenge.points for s in self.solves)

    def has_solved(self, challenge_id):
        return any(s.challenge_id == challenge_id for s in self.solves)


class Challenge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(32), nullable=False, default="misc")
    difficulty = db.Column(db.String(16), nullable=False, default="easy")
    description = db.Column(db.Text, nullable=False, default="")
    points = db.Column(db.Integer, nullable=False, default=100)
    flag = db.Column(db.String(256), nullable=False)
    # Key linking to a built-in lab. None for challenges created by admins.
    lab_key = db.Column(db.String(32), unique=True, nullable=True)
    url = db.Column(db.String(256), nullable=True)
    # Who wrote the challenge (shown as a credit). Optional.
    author = db.Column(db.String(64), nullable=True)
    visible = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    solves = db.relationship(
        "Solve", back_populates="challenge", cascade="all, delete-orphan",
        order_by="Solve.solved_at",
    )
    submissions = db.relationship(
        "Submission", back_populates="challenge", cascade="all, delete-orphan"
    )

    def check_flag(self, submitted):
        return hmac.compare_digest(submitted.strip().encode(), self.flag.strip().encode())


class Solve(db.Model):
    __table_args__ = (db.UniqueConstraint("user_id", "challenge_id"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    challenge_id = db.Column(db.Integer, db.ForeignKey("challenge.id"), nullable=False)
    solved_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    user = db.relationship("User", back_populates="solves")
    challenge = db.relationship("Challenge", back_populates="solves")


class Submission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    challenge_id = db.Column(db.Integer, db.ForeignKey("challenge.id"), nullable=False)
    content = db.Column(db.String(256), nullable=False)
    correct = db.Column(db.Boolean, nullable=False)
    ip = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)

    user = db.relationship("User", back_populates="submissions")
    challenge = db.relationship("Challenge", back_populates="submissions")


def scoreboard(limit=None):
    """List of (user, score, solve_count, last_solve). Highest score first; ties go to whoever got there first."""
    score = func.coalesce(func.sum(Challenge.points), 0).label("score")
    last = func.max(Solve.solved_at).label("last")
    count = func.count(Solve.id).label("count")
    q = (
        db.session.query(User, score, count, last)
        .outerjoin(Solve, Solve.user_id == User.id)
        .outerjoin(Challenge, Challenge.id == Solve.challenge_id)
        .filter(User.hidden.is_(False), User.is_admin.is_(False))
        .group_by(User.id)
        .order_by(desc("score"), asc("last"), asc(User.id))
    )
    if limit:
        q = q.limit(limit)
    return q.all()
