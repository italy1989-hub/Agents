from urllib.parse import urlparse

from core import bitrix as bx


def card_url(kind: str, entity_id: int) -> str:
    """kind: company | contact | deal"""
    u = urlparse(bx.BITRIX_WEBHOOK or "")
    return f"{u.scheme}://{u.netloc}/crm/{kind}/details/{entity_id}/"
