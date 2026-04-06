import requests as req
from functools import lru_cache

URL = "https://ygocdb.com"
REQUEST_TIMEOUT = 2.5

_session = req.Session()

def get_card_original_data(card_id):
    try:
        response = _session.get(f"{URL}/api/v0/card/{card_id}", timeout=REQUEST_TIMEOUT)
    except req.RequestException:
        return None
    if response.status_code != 200:
        return None
    return response.json()
    
def get_card_data(original_data):
    if not original_data:
        return None

    def get_type(type_code):
        class CardType:
            UNKNOWN = 0x0
            MONSTER = 0x1
            SPELL = 0x2
            TRAP = 0x4
        if type_code & CardType.MONSTER:
            return CardType.MONSTER
        elif type_code & CardType.SPELL:
            return CardType.SPELL
        elif type_code & CardType.TRAP:
            return CardType.TRAP
        else:
            return CardType.UNKNOWN
    return {
        "id": original_data.get("id"),
        "name": original_data.get("text", {}).get("name", "未知卡片"),
        "type": get_type(original_data.get("data", {}).get("type", 0))
    }
    
def get_card_data_by_id(card_id):
    return _get_card_data_by_id_cached(int(card_id))


@lru_cache(maxsize=4096)
def _get_card_data_by_id_cached(card_id):
    card_data = get_card_original_data(card_id)
    return get_card_data(card_data)

def get_card_data_by_name(card_name):
    if not card_name:
        return None
    try:
        response = _session.get(f"{URL}/api/v0", params={"search": card_name}, timeout=REQUEST_TIMEOUT)
    except req.RequestException:
        return None
    if response.status_code == 200:
        cards = response.json()['result']
        if cards:
            return get_card_data(cards[0])
    return None
