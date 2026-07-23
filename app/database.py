from sqlalchemy import text

from .extensions import db


INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS idx_ban_list_region_date "
    "ON ban_list(region, effective_date)",
    "CREATE INDEX IF NOT EXISTS idx_ban_list_card_ban_list_cid "
    "ON ban_list_card(ban_list_id, cid)",
    "CREATE INDEX IF NOT EXISTS idx_ban_list_card_region_date "
    "ON ban_list_card(region, date_added)",
    "CREATE INDEX IF NOT EXISTS idx_ban_list_change_ban_list_card "
    "ON ban_list_card_change(ban_list_id, card_id)",
)


def initialize_database():
    db.create_all()
    for statement in INDEX_STATEMENTS:
        db.session.execute(text(statement))
    db.session.commit()
