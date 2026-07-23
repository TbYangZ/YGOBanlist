import datetime
from dataclasses import dataclass

from ..config import STATUS_MAP
from ..extensions import db
from ..models import BanList, BanListCard, BanListCardChange
from . import catalog


class BanListServiceError(Exception):
    pass


class BanListNotFound(BanListServiceError):
    pass


class BanListConflict(BanListServiceError):
    pass


class InvalidCard(BanListServiceError):
    pass


@dataclass(frozen=True)
class ImportResult:
    added: int
    updated: int


@dataclass(frozen=True)
class CardMutationResult:
    action: str
    cid: int
    name: str


def get_exact(region, effective_date, create=False):
    ban_list = BanList.query.filter_by(
        region=region,
        effective_date=effective_date,
    ).first()
    if ban_list is None and create:
        ban_list = BanList(region=region, effective_date=effective_date)
        db.session.add(ban_list)
        db.session.flush()
    return ban_list


def get_for_year(region, year):
    start_date = datetime.date(year, 1, 1)
    end_date = datetime.date(year, 12, 31)
    return (
        BanList.query
        .filter(BanList.region == region)
        .filter(BanList.effective_date >= start_date)
        .filter(BanList.effective_date <= end_date)
        .order_by(BanList.effective_date.asc())
        .all()
    )


def select_for_year(region, year, effective_date=None):
    year_ban_lists = get_for_year(region, year)
    if effective_date is not None:
        selected = next(
            (
                ban_list
                for ban_list in year_ban_lists
                if ban_list.effective_date == effective_date
            ),
            None,
        )
        if selected is not None:
            return selected, year_ban_lists
    return (
        year_ban_lists[-1] if year_ban_lists else None,
        year_ban_lists,
    )


def sync_change(ban_list_id, card_id, old_status, new_status):
    change = BanListCardChange.query.filter_by(
        ban_list_id=ban_list_id,
        card_id=card_id,
    ).first()
    if change is None:
        change = BanListCardChange(
            ban_list_id=ban_list_id,
            card_id=card_id,
            old_status=old_status,
            new_status=new_status,
        )
        db.session.add(change)
    else:
        change.old_status = old_status
        change.new_status = new_status
    return change


def _validate_statuses(old_status, new_status):
    if old_status not in STATUS_MAP or new_status not in STATUS_MAP:
        raise InvalidCard("状态值不合法。")


def _normalize_row(row):
    try:
        cid = int(row.get("id", 0))
        old_status = int(row.get("past", 3))
        new_status = int(row.get("current", 3))
    except (TypeError, ValueError) as exc:
        raise InvalidCard("CSV 中存在无效卡片数据。") from exc

    if cid <= 0:
        raise InvalidCard("CSV 中存在无效的卡片 CID。")
    _validate_statuses(old_status, new_status)
    return cid, old_status, new_status


def _upsert_row(ban_list, row, existing_map):
    cid, old_status, new_status = _normalize_row(row)
    card = existing_map.get(cid)
    if card is None:
        card = BanListCard(
            cid=cid,
            ban_list_id=ban_list.id,
            status=new_status,
            date_added=ban_list.effective_date,
            region=ban_list.region,
        )
        db.session.add(card)
        db.session.flush()
        existing_map[cid] = card
        action = "added"
    else:
        card.status = new_status
        card.date_added = ban_list.effective_date
        card.region = ban_list.region
        action = "updated"

    sync_change(ban_list.id, card.id, old_status, new_status)
    return action


def create_ban_list(region, effective_date, rows=None):
    existing = get_exact(region, effective_date)
    if existing is not None:
        return existing, 0, False

    ban_list = BanList(region=region, effective_date=effective_date)
    db.session.add(ban_list)
    db.session.flush()

    added = 0
    existing_map = {}
    try:
        for row in rows or []:
            if _upsert_row(ban_list, row, existing_map) == "added":
                added += 1
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return ban_list, added, True


def change_effective_date(region, old_date, new_date):
    ban_list = get_exact(region, old_date)
    if ban_list is None:
        raise BanListNotFound("未找到要修改时间的禁卡表。")
    if old_date == new_date:
        return False
    if get_exact(region, new_date) is not None:
        raise BanListConflict(f"{new_date.isoformat()} 已存在禁卡表，无法修改。")

    try:
        ban_list.effective_date = new_date
        for card in ban_list.cards:
            card.date_added = new_date
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return True


def delete_ban_list(region, effective_date):
    ban_list = get_exact(region, effective_date)
    if ban_list is None:
        raise BanListNotFound("未找到要删除的禁卡表。")
    try:
        db.session.delete(ban_list)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


def mutate_card(
    operation,
    region,
    effective_date,
    *,
    card_id=None,
    cid=None,
    name="",
    old_status=3,
    new_status=3,
    notes=None,
):
    if operation not in {"add", "update", "delete"}:
        raise InvalidCard("不支持的操作类型。")

    ban_list = get_exact(region, effective_date, create=operation == "add")
    if ban_list is None:
        raise BanListNotFound("该时间点还没有禁卡表，请先新增卡片。")

    try:
        if operation == "add":
            return _add_or_update_card(
                ban_list,
                cid=cid,
                name=name,
                old_status=old_status,
                new_status=new_status,
                notes=notes,
            )
        return _update_or_delete_card(
            ban_list,
            operation=operation,
            card_id=card_id,
            old_status=old_status,
            new_status=new_status,
            notes=notes,
        )
    except Exception:
        db.session.rollback()
        raise


def _add_or_update_card(
    ban_list,
    *,
    cid,
    name,
    old_status,
    new_status,
    notes,
):
    _validate_statuses(old_status, new_status)
    if cid in (None, "") and not name:
        raise InvalidCard("请至少提供 CID 或卡名中的一个。")

    if cid in (None, ""):
        card_data = catalog.find_card(name)
        if card_data is None:
            raise InvalidCard("未找到对应卡片，请检查卡名是否正确。")
        cid = card_data["id"]
    try:
        cid = int(cid)
    except (TypeError, ValueError) as exc:
        raise InvalidCard("CID 必须是有效数字。") from exc
    if cid <= 0:
        raise InvalidCard("CID 必须是有效数字。")

    card = BanListCard.query.filter_by(
        ban_list_id=ban_list.id,
        cid=cid,
    ).first()
    action = "added"
    if card is None:
        card = BanListCard(
            cid=cid,
            ban_list_id=ban_list.id,
            status=new_status,
            date_added=ban_list.effective_date,
            region=ban_list.region,
            notes=notes,
        )
        db.session.add(card)
        db.session.flush()
    else:
        action = "updated"
        card.status = new_status
        card.date_added = ban_list.effective_date
        card.region = ban_list.region
        if notes is not None:
            card.notes = notes

    sync_change(ban_list.id, card.id, old_status, new_status)
    db.session.commit()
    return CardMutationResult(action, cid, catalog.card_name(cid))


def _update_or_delete_card(
    ban_list,
    *,
    operation,
    card_id,
    old_status,
    new_status,
    notes,
):
    try:
        card_id = int(card_id)
    except (TypeError, ValueError) as exc:
        raise InvalidCard("卡片记录参数不合法。") from exc

    card = BanListCard.query.filter_by(
        id=card_id,
        ban_list_id=ban_list.id,
    ).first()
    if card is None:
        raise InvalidCard(
            "未找到要删除的卡片。" if operation == "delete"
            else "未找到要更新的卡片。"
        )

    name = catalog.card_name(card.cid)
    cid = card.cid
    if operation == "delete":
        db.session.delete(card)
    else:
        _validate_statuses(old_status, new_status)
        card.status = new_status
        card.notes = notes
        sync_change(ban_list.id, card.id, old_status, new_status)

    db.session.commit()
    return CardMutationResult(
        "deleted" if operation == "delete" else "updated",
        cid,
        name,
    )


def import_rows(region, effective_date, rows, mode):
    if mode not in {"append", "overwrite"}:
        raise BanListServiceError("上传模式不合法。")

    ban_list = get_exact(region, effective_date, create=True)
    try:
        if mode == "overwrite":
            for card in list(ban_list.cards):
                db.session.delete(card)
            db.session.flush()
            existing_map = {}
        else:
            existing_map = {card.cid: card for card in ban_list.cards}

        added = 0
        updated = 0
        for row in rows:
            action = _upsert_row(ban_list, row, existing_map)
            if action == "added":
                added += 1
            else:
                updated += 1
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return ImportResult(added=added, updated=updated)
