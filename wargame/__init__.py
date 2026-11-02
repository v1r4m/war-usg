import os
import secrets
from datetime import timedelta

import click
from flask import Flask, render_template

from .extensions import csrf, db, login_manager
from .models import User


def _load_secret_key(instance_path):
    """환경변수 SECRET_KEY 우선, 없으면 instance/secret_key 파일에 생성해 재사용."""
    if os.environ.get("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    path = os.path.join(instance_path, "secret_key")
    if os.path.exists(path):
        with open(path) as f:
            return f.read().strip()
    key = secrets.token_hex(32)
    with open(path, "w") as f:
        f.write(key)
    os.chmod(path, 0o600)
    return key


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    os.makedirs(app.instance_path, exist_ok=True)

    app.config.update(
        SECRET_KEY=_load_secret_key(app.instance_path),
        SQLALCHEMY_DATABASE_URI=os.environ.get(
            "DATABASE_URL", "sqlite:///" + os.path.join(app.instance_path, "wargame.db")
        ),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE") == "1",
        REMEMBER_COOKIE_HTTPONLY=True,
        PERMANENT_SESSION_LIFETIME=timedelta(days=7),
        SITE_NAME=os.environ.get("SITE_NAME", "USG Wargame"),
        # 1분에 허용할 플래그 제출 횟수 (브루트포스 방지)
        SUBMIT_RATE_LIMIT=int(os.environ.get("SUBMIT_RATE_LIMIT", "10")),
    )
    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "로그인이 필요합니다."
    login_manager.login_message_category = "info"

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    from .admin import bp as admin_bp
    from .auth import bp as auth_bp
    from .labs import bp as labs_bp
    from .main import bp as main_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(labs_bp)
    # 실습 문제는 일부러 취약하게 만든 것이라 CSRF 검사에서 제외
    csrf.exempt(labs_bp)

    @app.template_filter("kst")
    def kst(dt):
        if dt is None:
            return "-"
        return (dt + timedelta(hours=9)).strftime("%Y-%m-%d %H:%M")

    @app.context_processor
    def inject_site():
        return {"site_name": app.config["SITE_NAME"]}

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("error.html", code=403, message="접근 권한이 없습니다."), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("error.html", code=404, message="페이지를 찾을 수 없습니다."), 404

    from .seed import seed_challenges

    with app.app_context():
        db.create_all()
        seed_challenges()

    @app.cli.command("create-admin")
    @click.argument("username")
    @click.password_option()
    def create_admin(username, password):
        """관리자 계정을 만들거나 기존 계정을 관리자로 승격합니다."""
        user = User.query.filter_by(username=username).first()
        if user is None:
            user = User(username=username)
            db.session.add(user)
        user.set_password(password)
        user.is_admin = True
        db.session.commit()
        click.echo(f"관리자 계정 준비 완료: {username}")

    @app.cli.command("reset-flags")
    def reset_flags():
        """내장 실습 문제의 플래그를 새로 랜덤 생성합니다 (기존 풀이 기록은 유지)."""
        from .seed import regenerate_lab_flags

        n = regenerate_lab_flags()
        click.echo(f"{n}개 문제의 플래그를 재생성했습니다.")

    return app
