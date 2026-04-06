import os

from flask import Flask
from sqlalchemy import text
from . import models
from . import route

def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "dev-secret-key"
    app.config["EDIT_PASSWORD"] = os.environ.get("EDIT_PASSWORD", "123456")
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///data.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db = models.db
    db.init_app(app)
    app.register_blueprint(route.main)
    with app.app_context():
        db.create_all()
        db.session.execute(text("CREATE INDEX IF NOT EXISTS idx_ban_list_region_date ON ban_list(region, effective_date)"))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS idx_ban_list_card_ban_list_cid ON ban_list_card(ban_list_id, cid)"))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS idx_ban_list_card_region_date ON ban_list_card(region, date_added)"))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS idx_ban_list_change_ban_list_card ON ban_list_card_change(ban_list_id, card_id)"))
        db.session.commit()
    return app