from datetime import date

from app.app import create_app
from app import models

app = create_app()

def add_card(cid, ban_list_id, old_status, new_status):
    with app.app_context():
        db = models.db
        card = models.BanListCard(cid=cid, ban_list_id=ban_list_id, status=new_status)
        db.session.add(card)
        db.session.flush()

        change = models.BanListCardChange(ban_list_id=ban_list_id, card_id=card.id, old_status=old_status, new_status=new_status)
        db.session.add(change)
        db.session.commit()

with app.app_context():
    db = models.db
    bl = models.BanList(region=1, effective_date=date(2026, 4, 1))
    db.session.add(bl)
    db.session.flush()

    b2 = models.BanList(region=1, effective_date=date(2026, 1, 1))
    db.session.add(b2)
    db.session.flush()
    db.session.commit()

    add_card(69272449, bl.id, 1, 0)
    add_card(69272449, b2.id, 3, 1)
    add_card(32061192, bl.id, 3, 2)