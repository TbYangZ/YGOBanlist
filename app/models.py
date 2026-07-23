from .extensions import db


class BanList(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    region = db.Column(db.Integer, nullable=False, index=True)
    effective_date = db.Column(db.Date, nullable=False, index=True)

    __table_args__ = (
        db.UniqueConstraint(
            "region",
            "effective_date",
            name="uq_ban_list_region_effective_date",
        ),
        db.Index("idx_ban_list_region_date", "region", "effective_date"),
    )

    cards = db.relationship(
        "BanListCard",
        back_populates="ban_list",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self):
        return f"<BanList {self.region} - {self.effective_date}>"


class BanListCard(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    cid = db.Column(db.Integer, nullable=False, index=True)
    ban_list_id = db.Column(
        db.Integer,
        db.ForeignKey("ban_list.id"),
        nullable=False,
        index=True,
    )
    status = db.Column(db.Integer, nullable=False)
    date_added = db.Column(db.Date, default=None, index=True)
    region = db.Column(db.Integer, default=None, index=True)
    notes = db.Column(db.String(255), nullable=True)

    __table_args__ = (
        db.UniqueConstraint(
            "ban_list_id",
            "cid",
            name="uq_ban_list_card_ban_list_id_cid",
        ),
        db.Index("idx_ban_list_card_region_date", "region", "date_added"),
    )

    ban_list = db.relationship("BanList", back_populates="cards")
    changes = db.relationship(
        "BanListCardChange",
        back_populates="card",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self):
        return f"<BanListCard {self.id} - {self.cid}>"


class BanListCardChange(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    ban_list_id = db.Column(
        db.Integer,
        db.ForeignKey("ban_list.id"),
        nullable=False,
        index=True,
    )
    card_id = db.Column(
        db.Integer,
        db.ForeignKey("ban_list_card.id"),
        nullable=False,
        index=True,
    )
    old_status = db.Column(db.Integer, nullable=False)
    new_status = db.Column(db.Integer, nullable=False)

    __table_args__ = (
        db.Index("idx_ban_list_change_ban_list_card", "ban_list_id", "card_id"),
    )

    card = db.relationship("BanListCard", back_populates="changes")

    def __repr__(self):
        return f"<BanListCardChange {self.card_id} - {self.old_status} to {self.new_status}>"
