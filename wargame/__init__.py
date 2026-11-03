import os
import secrets
from datetime import timedelta

import click
from flask import Flask, render_template

from .extensions import csrf, db, login_manager
from .models import User


def _load_secret_key(instance_path):
    """Use SECRET_KEY from the environment, else create and reuse instance/secret_key."""
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


def _bootstrap_admin():
    """If ADMIN_USERNAME / ADMIN_PASSWORD are set, create that admin only when the account doesn't exist yet."""
    username = os.environ.get("ADMIN_USERNAME", "").strip()
    password = os.environ.get("ADMIN_PASSWORD", "")
    if not username or not password:
        return
    if User.query.filter_by(username=username).first():
        return
    if len(password) < 8:
        raise RuntimeError("ADMIN_PASSWORD must be at least 8 characters.")
    user = User(username=username, is_admin=True)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()


def _migrate():
    """create_all() never adds columns to existing tables, so add the ones introduced later."""
    from sqlalchemy import inspect, text

    cols = {c["name"] for c in inspect(db.engine).get_columns("challenge")}
    with db.engine.begin() as conn:
        if "author" not in cols:
            conn.execute(text("ALTER TABLE challenge ADD COLUMN author VARCHAR(64)"))


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
        SITE_NAME=os.environ.get("SITE_NAME", "最強海巨"),
        # flag submissions allowed per minute (brute-force protection)
        SUBMIT_RATE_LIMIT=int(os.environ.get("SUBMIT_RATE_LIMIT", "10")),
    )
    if test_config:
        app.config.update(test_config)

    # Trust X-Forwarded-* from a reverse proxy such as Coolify (Traefik) to see the real IP/HTTPS
    proxies = int(os.environ.get("TRUSTED_PROXIES", "0"))
    if proxies > 0:
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(
            app.wsgi_app, x_for=proxies, x_proto=proxies, x_host=proxies, x_port=proxies
        )

    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in first."
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
    # Labs are intentionally vulnerable, so they are exempt from CSRF checks
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
        return render_template("error.html", code=403, message="You don't have access to this page."), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("error.html", code=404, message="Page not found."), 404

    from .seed import seed_challenges

    @app.route("/healthz")
    def healthz():
        return {"status": "ok"}

    with app.app_context():
        db.create_all()
        _migrate()
        seed_challenges()
        _bootstrap_admin()
        # Drop pooled connections so workers forked by gunicorn --preload don't share them
        db.engine.dispose()

    @app.cli.command("create-admin")
    @click.argument("username")
    @click.password_option()
    def create_admin(username, password):
        """Create an admin account, or promote an existing account to admin."""
        user = User.query.filter_by(username=username).first()
        if user is None:
            user = User(username=username)
            db.session.add(user)
        user.set_password(password)
        user.is_admin = True
        db.session.commit()
        click.echo(f"Admin account ready: {username}")

    @app.cli.command("reset-flags")
    def reset_flags():
        """Regenerate random flags for the built-in labs (existing solves are kept)."""
        from .seed import regenerate_lab_flags

        n = regenerate_lab_flags()
        click.echo(f"Regenerated flags for {n} challenges.")
        from .s3lab import bucket_name, fixed_flag

        if bucket_name() and not fixed_flag():
            click.echo("S3_LAB_FLAG is not set: run `flask s3-script` again and re-upload the bucket.")

    @app.cli.command("s3-script")
    @click.option("--purge-only", is_flag=True, help="Only empty the bucket (e.g. before deleting it).")
    def s3_script(purge_only):
        """Print a script for AWS CloudShell that uploads the S3 lab (with its flag) to S3_LAB_BUCKET."""
        from .models import Challenge
        from .s3lab import LAB_KEY, bucket_name, cloudshell_script

        if not bucket_name():
            raise click.ClickException("Set S3_LAB_BUCKET first.")
        chal = Challenge.query.filter_by(lab_key=LAB_KEY).first()
        if chal is None:
            raise click.ClickException("The S3 lab challenge does not exist.")
        click.echo(cloudshell_script(chal.flag, purge_only=purge_only), nl=False)

    return app
