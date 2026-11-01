"""Optional TON / NFT verification hooks.

We deliberately do **not** claim any gift is an NFT. This module only verifies
addresses against the public TON API; minting requires a deployed, audited
collection contract and is out of scope for the application code.
"""

from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.models import Collection

logger = get_logger(__name__)


class TonError(Exception):
    pass


def _headers() -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if settings.tonapi_key:
        headers["Authorization"] = f"Bearer {settings.tonapi_key}"
    return headers


def is_enabled() -> bool:
    return bool(settings.tonapi_base_url)


def normalize_address(address: str) -> str:
    address = address.strip()
    if not address:
        raise TonError("Укажите адрес TON")
    if len(address) > 80 or any(ch.isspace() for ch in address):
        raise TonError("Некорректный адрес TON")
    if not address.startswith(("EQ", "UQ", "0:", "-1:")):
        raise TonError("Поддерживаются friendly-адреса (EQ…/UQ…) или raw-адреса (0:…)")
    return address


def fetch_account(address: str) -> dict:
    if not is_enabled():
        raise TonError("TON-интеграция не настроена (TONAPI_BASE_URL)")
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(
                f"{settings.tonapi_base_url.rstrip('/')}/v2/accounts/{address}",
                headers=_headers(),
            )
    except httpx.HTTPError as exc:
        raise TonError(f"TON API недоступен: {exc}") from exc
    if response.status_code == 404:
        raise TonError("Адрес не найден в блокчейне TON")
    if response.status_code >= 400:
        raise TonError(f"TON API вернул ошибку {response.status_code}")
    return response.json()


def verify_wallet(address: str) -> dict:
    data = fetch_account(normalize_address(address))
    return {
        "address": address,
        "exists": True,
        "balance_nanoton": data.get("balance", 0),
        "status": data.get("status", "unknown"),
    }


def verify_collection_onchain(collection: Collection, address: str) -> Collection:
    """Confirm a collection address exists on TON and store it.

    This proves the address exists; it does **not** prove that GIFT MARKET
    items were minted into it. Only mark ``chain_verified`` after you have
    confirmed the mint transactions for the specific items.
    """
    address = normalize_address(address)
    fetch_account(address)
    collection.ton_collection_address = address
    collection.chain_verified = True
    logger.info(
        "ton.collection_verified",
        extra={"event": f"collection={collection.id} address={address}"},
    )
    return collection


def nft_link(address: str) -> str:
    return f"https://tonviewer.com/{address}" if address else ""
