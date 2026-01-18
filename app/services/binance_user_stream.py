# app/services/binance_user_stream.py
import httpx


def start_user_stream(base_url: str, api_key: str) -> str:
    """
    Create a listenKey for Binance User Data Stream.

    IMPORTANT:
    In this project base_url already ends with '/api' (e.g. https://testnet.binance.vision/api),
    so the correct endpoint is:
      POST {base_url}/v3/userDataStream
    """
    url = f"{base_url}/v3/userDataStream"
    headers = {"X-MBX-APIKEY": api_key}

    with httpx.Client(timeout=6.0) as client:
        r = client.post(url, headers=headers)
        r.raise_for_status()
        data = r.json()

    listen_key = data.get("listenKey")
    if not listen_key:
        raise RuntimeError("No listenKey returned from Binance")
    return listen_key


def keepalive_user_stream(base_url: str, api_key: str, listen_key: str) -> None:
    """
    Keepalive a listenKey.

    Correct endpoint with our base_url style:
      PUT {base_url}/v3/userDataStream?listenKey=...
    """
    url = f"{base_url}/v3/userDataStream"
    headers = {"X-MBX-APIKEY": api_key}
    params = {"listenKey": listen_key}

    with httpx.Client(timeout=6.0) as client:
        r = client.put(url, headers=headers, params=params)
        r.raise_for_status()