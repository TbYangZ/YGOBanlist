from .. import card_info


UNKNOWN_CARD = {
    "id": None,
    "name": "未知卡片",
    "type": 0,
}


def get_card(cid):
    return card_info.get_card_data_by_id(cid)


def find_card(name):
    return card_info.get_card_data_by_name(name)


def get_card_map(cids):
    return {
        cid: get_card(cid)
        for cid in set(cids)
    }


def card_name(cid):
    card = get_card(cid)
    return card.get("name", UNKNOWN_CARD["name"]) if card else UNKNOWN_CARD["name"]
