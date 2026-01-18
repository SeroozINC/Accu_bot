# app/services/binance_rest.py
import hmac
import hashlib
import time
from urllib.parse import urlencode

import httpx

TESTNET_BASE = "https://testnet.binance.vision/api"  # Spot Testnet REST base
MAINNET_BASE = "https://api.binance.com/api"


def _sign(secret: str, query_string: str) -> str:
    return hmac.new(secret.encode("utf-8"), query_string.encode("utf-8"), hashlib.sha256).hexdigest()


def signed_get(
    base_url: str,
    path: str,
    api_key: str,
    api_secret: str,
    params: dict | None = None,
    timeout_s: float = 5.0,
) -> dict:
    if params is None:
        params = {}

    params = dict(params)
    params["timestamp"] = int(time.time() * 1000)
    params["recvWindow"] = 5000

    qs = urlencode(params)
    signature = _sign(api_secret, qs)
    url = f"{base_url}{path}?{qs}&signature={signature}"

    headers = {"X-MBX-APIKEY": api_key}

    with httpx.Client(timeout=timeout_s) as client:
        r = client.get(url, headers=headers)
        r.raise_for_status()
        return r.json()


def get_account(base_url: str, api_key: str, api_secret: str) -> dict:
    return signed_get(base_url, "/v3/account", api_key, api_secret)


def extract_balances(account_json: dict, min_free: float = 0.0) -> list[dict]:
    out = []
    for b in account_json.get("balances", []):
        try:
            free = float(b.get("free", "0"))
            locked = float(b.get("locked", "0"))
        except Exception:
            continue
        if free > min_free or locked > 0:
            out.append({"asset": b.get("asset"), "free": free, "locked": locked})
    return out