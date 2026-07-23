from datetime import date

from app import create_app
from app.services import banlists


def seed():
    app = create_app()
    with app.app_context():
        april, _, _ = banlists.create_ban_list(1, date(2026, 4, 1))
        january, _, _ = banlists.create_ban_list(1, date(2026, 1, 1))
        banlists.mutate_card(
            "add",
            april.region,
            april.effective_date,
            cid=69272449,
            old_status=1,
            new_status=0,
        )
        banlists.mutate_card(
            "add",
            january.region,
            january.effective_date,
            cid=69272449,
            old_status=3,
            new_status=1,
        )
        banlists.mutate_card(
            "add",
            april.region,
            april.effective_date,
            cid=32061192,
            old_status=3,
            new_status=2,
        )


if __name__ == "__main__":
    seed()
