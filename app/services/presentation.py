import datetime

from .. import config
from ..models import BanListCardChange
from . import banlists, catalog


def classify_full_change(old_status, new_status):
    if old_status is None or new_status is None or old_status == new_status:
        return "", ""
    if old_status == 3 and new_status == 0:
        return "新规禁止", "change-tight"
    if old_status == 3 and new_status == 1:
        return "新规限制", "change-tight"
    if old_status == 3 and new_status == 2:
        return "新规准限制", "change-tight"
    if new_status == 0:
        return "新规禁止", "change-tight"
    label = f"{config.STATUS_MAP[old_status]}=>{config.STATUS_MAP[new_status]}"
    return label, "change-tight" if new_status < old_status else "change-loose"


def classify_change(old_status, new_status):
    if old_status is None or new_status is None or old_status == new_status:
        return "", ""
    if old_status == 3:
        return "新规指定", "change-tight"
    if new_status == 3:
        return "限制解除", "change-loose"
    if old_status > new_status:
        return "限制加强", "change-tight"
    return "限制缓和", "change-loose"


def card_type_order(card_type):
    return {1: 0, 2: 1, 3: 2, 0: 9}.get(card_type, 9)


def change_label_order(label):
    labels = (
        "新规禁止",
        "新规限制",
        "新规准限制",
        "禁止=>限制",
        "禁止=>准限制",
        "限制=>准限制",
        "限制=>无限制",
        "准限制=>无限制",
        "准限制=>限制",
        "限制=>禁止",
        "准限制=>禁止",
        "无限制=>限制",
        "无限制=>准限制",
    )
    return {value: index for index, value in enumerate(labels)}.get(label, 99)


def _selected_ban_list(selection):
    requested_date = selection.effective_date
    if requested_date is not None and requested_date.year != selection.year:
        requested_date = None
    return banlists.select_for_year(
        selection.region,
        selection.year,
        requested_date,
    )


def _base_context(selection, selected, year_ban_lists):
    selected_date = selected.effective_date.isoformat() if selected else ""
    return {
        "selected_year": selection.year,
        "selected_region": selection.region,
        "selected_mode": selection.mode,
        "selected_effective_date": selected_date,
        "year_ban_lists": year_ban_lists,
        "year_options": list(
            range(max(datetime.date.today().year, selection.year), 2003, -1)
        ),
        "status_map": config.STATUS_MAP,
        "status_class_map": config.STATUS_CLASS_MAP,
        "region_map": config.BANLIST_REGIONS,
    }


def public_page(selection):
    selected, year_ban_lists = _selected_ban_list(selection)
    context = _base_context(selection, selected, year_ban_lists)

    if selection.mode == "full":
        context["status_sections"] = build_full_sections(selected)
        return "full.html", context

    context["cards"] = build_change_cards(selected)
    context["ban_list"] = selected
    return "changes.html", context


def build_full_sections(ban_list):
    grouped = {status: [] for status in config.STATUS_MAP}
    if ban_list is not None:
        card_map = catalog.get_card_map(card.cid for card in ban_list.cards)
        for card in ban_list.cards:
            card_data = card_map.get(card.cid)
            change = next(
                (
                    item
                    for item in card.changes
                    if item.ban_list_id == ban_list.id
                ),
                None,
            )
            old_status = change.old_status if change else card.status
            label, css_class = (
                classify_full_change(old_status, card.status)
                if change else ("", "")
            )
            grouped[card.status].append({
                "id": card.cid,
                "name": card_data["name"] if card_data else "未知卡片",
                "type": card_data["type"] if card_data else 0,
                "status": card.status,
                "old_status": old_status,
                "notes": card.notes or "",
                "change_label": label,
                "change_class": css_class,
            })

    return [
        {
            "status": status,
            "title": config.STATUS_MAP[status],
            "cards": sorted(
                grouped[status],
                key=lambda item: (
                    card_type_order(item.get("type", 0)),
                    item["id"],
                ),
            ),
        }
        for status in config.STATUS_MAP
    ]


def build_change_cards(ban_list):
    if ban_list is None:
        return []

    changes = BanListCardChange.query.filter_by(ban_list_id=ban_list.id).all()
    cards_by_id = {card.id: card for card in ban_list.cards}
    card_map = catalog.get_card_map(
        card.cid
        for card in cards_by_id.values()
    )

    payloads = []
    for change in changes:
        card = cards_by_id.get(change.card_id)
        if card is None:
            continue
        card_data = card_map.get(card.cid)
        label, css_class = classify_change(change.old_status, change.new_status)
        payloads.append({
            "id": card.cid,
            "name": card_data["name"] if card_data else "未知卡片",
            "type": card_data["type"] if card_data else 0,
            "old_status": change.old_status,
            "status": change.new_status,
            "notes": card.notes or "",
            "change_label": label,
            "change_class": css_class,
        })

    return sorted(
        payloads,
        key=lambda item: (
            item["status"],
            change_label_order(item.get("change_label", "")),
            card_type_order(item.get("type", 0)),
            item["id"],
        ),
    )


def editor_page(selection, authenticated):
    selected, year_ban_lists = _selected_ban_list(selection)
    context = _base_context(selection, selected, year_ban_lists)
    context.update({
        "edit_authenticated": authenticated,
        "ban_list": selected,
        "cards": build_editor_cards(selected),
    })
    return context


def build_editor_cards(ban_list):
    if ban_list is None:
        return []

    card_map = catalog.get_card_map(card.cid for card in ban_list.cards)
    payloads = []
    for card in ban_list.cards:
        change = next(
            (
                item
                for item in card.changes
                if item.ban_list_id == ban_list.id
            ),
            None,
        )
        card_data = card_map.get(card.cid)
        payloads.append({
            "ban_card_id": card.id,
            "cid": card.cid,
            "name": card_data["name"] if card_data else "未知卡片",
            "old_status": change.old_status if change else card.status,
            "status": card.status,
            "notes": card.notes,
        })
    return sorted(payloads, key=lambda item: (item["status"], item["cid"]))
