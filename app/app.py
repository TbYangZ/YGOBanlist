import os

from flask import Flask
from dotenv import load_dotenv
from werkzeug.middleware.proxy_fix import ProxyFix

from . import models
from .database import initialize_database
from .extensions import db
from .routes.editor import editor
from .routes.public import public


def create_app(test_config=None):
    load_dotenv()
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-secret-key"),
        EDIT_PASSWORD=os.environ.get("EDIT_PASSWORD", "123456"),
        SQLALCHEMY_DATABASE_URI=os.environ.get(
            "SQLALCHEMY_DATABASE_URI",
            "sqlite:///data.db",
        ),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    if test_config:
        app.config.update(test_config)

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    session_cookie_path = os.environ.get("SESSION_COOKIE_PATH", "").strip()
    if session_cookie_path:
        app.config["SESSION_COOKIE_PATH"] = session_cookie_path

    db.init_app(app)
    app.register_blueprint(public)
    app.register_blueprint(editor)

    with app.app_context():
        initialize_database()

    return app
