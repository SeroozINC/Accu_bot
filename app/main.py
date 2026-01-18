# app/main.py
import os
import json
import time

import httpx
import websockets
from dotenv import load_dotenv
from passlib.context import CryptContext
from starlette.middleware.sessions import SessionMiddleware

from fastapi import FastAPI, Request, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.connections.db_connections import init_db, log_event, get_events

from app.services.binance_rest import (
    TESTNET_BASE,
    MAINNET_BASE,
    signed_get,
    get_account,
    extract_balances,
)
from app.services.binance_user_stream import start_user_stream, keepalive_user_stream

from app.models.user_profile_db import (
    init_userprofile_db,
    get_user_profile,
    upsert_user_profile_base,
    update_binance_credentials,
    update_binance_listenkey,
)

# --- ENV / CONFIG ---
load_dotenv()

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

SESSION_SECRET = os.getenv("SESSION_SECRET", "")
AUTH_USERNAME = os.getenv("ADMIN_USERNAME", "")
AUTH_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH", "")

CMC_API_KEY = os.getenv("CMC_API_KEY", "")
CMC_CONVERT = os.getenv("CMC_CONVERT", "USD")
CMC_URL = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"

_prices_cache = {"ts": 0.0, "data": None}
PRICES_TTL_SECONDS = 10

if not SESSION_SECRET:
    raise RuntimeError("Missing SESSION_SECRET in .env")
if not AUTH_USERNAME or not AUTH_PASSWORD_HASH:
    raise RuntimeError("Missing ADMIN_USERNAME or ADMIN_PASSWORD_HASH in .env")

# --- APP SETUP ---
app = FastAPI()
templates = Jinja2Templates(directory="ui/templates")
app.mount("/static", StaticFiles(directory="ui/static"), name="static")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)

# ==== Token Whitelist ====
BINANCE_BALANCE_ASSETS = {"BTC", "ETH", "USDC", "ADA", "TRX"}


# --- AUTH HELPERS ---
def is_logged_in(request: Request) -> bool:
    return bool(request.session.get("user"))


def require_login(request: Request):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=303)
    return None


def ws_get_user_email(websocket: WebSocket) -> str | None:
    sess = websocket.scope.get("session")
    if not sess:
        return None
    return sess.get("user")


def _get_profile_dict(user_email: str | None) -> dict | None:
    if not user_email:
        return None
    row = get_user_profile(user_email)
    return dict(row) if row else None


# --- CONFIGURED EXCHANGES HELPERS ---
def build_configured_exchanges(profile: dict | None) -> list[dict]:
    items: list[dict] = []
    if not profile:
        return items

    if profile.get("testnetAPIKey") and profile.get("testnetAPISecret"):
        items.append(
            {"id": "binance:testnet", "label": "Binance (Testnet)", "exchange": "binance", "env": "testnet"}
        )

    if profile.get("mainnetAPIKey") and profile.get("mainnetAPISecret"):
        items.append(
            {"id": "binance:mainnet", "label": "Binance (Mainnet)", "exchange": "binance", "env": "mainnet"}
        )

    return items


def parse_exchange_id(exchange_id: str | None) -> tuple[str | None, str | None]:
    if not exchange_id or ":" not in exchange_id:
        return None, None
    ex, env = exchange_id.split(":", 1)
    return ex.strip().lower(), env.strip().lower()


def _get_active_exchange_id(request: Request, items: list[dict]) -> str | None:
    configured_ids = {i["id"] for i in items}
    active = request.session.get("active_exchange_id")
    if active not in configured_ids:
        active = items[0]["id"] if items else None
        request.session["active_exchange_id"] = active
    return active


# --- LIFECYCLE ---
@app.on_event("startup")
def on_startup():
    init_db()
    init_userprofile_db()
    log_event("Bot Initializing", level="INFO")


# --- AUTHENTICATION ---
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if is_logged_in(request):
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": None, "user": None})


@app.post("/login", response_class=HTMLResponse)
def login_action(request: Request, username: str = Form(...), password: str = Form(...)):
    if username == AUTH_USERNAME and pwd_context.verify(password, AUTH_PASSWORD_HASH):
        request.session["user"] = username
        log_event(f"Login success: {username}", level="INFO")
        return RedirectResponse(url="/", status_code=303)

    log_event(f"Login failed: {username}", level="WARNING")
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": "Invalid username or password", "user": None},
    )


@app.post("/logout")
def logout(request: Request):
    user = request.session.get("user")
    request.session.clear()
    if user:
        log_event(f"Logout: {user}", level="INFO")
    return RedirectResponse(url="/login", status_code=303)


# --- WEB UI ---
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    r = require_login(request)
    if r:
        return r
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "user": request.session.get("user"), "active_page": "dashboard"},
    )


@app.get("/statistics", response_class=HTMLResponse)
def statistics(request: Request):
    r = require_login(request)
    if r:
        return r
    return templates.TemplateResponse(
        "statistics.html",
        {"request": request, "user": request.session.get("user"), "active_page": "statistics"},
    )


@app.get("/configuration", response_class=HTMLResponse)
def configuration(request: Request):
    r = require_login(request)
    if r:
        return r

    user_email = request.session.get("user")
    profile = _get_profile_dict(user_email)

    def has_value(d: dict | None, col: str) -> bool:
        return bool(d and d.get(col))

    context = {
        "request": request,
        "user": user_email,
        "active_page": "configuration",
        "binance_mainnet_saved": has_value(profile, "mainnetAPIKey") and has_value(profile, "mainnetAPISecret"),
        "binance_testnet_saved": has_value(profile, "testnetAPIKey") and has_value(profile, "testnetAPISecret"),
        "profile_updated": profile.get("dateUpdated") if profile else None,
        "saved_msg": request.query_params.get("saved"),
        "error_msg": request.query_params.get("error"),
    }
    return templates.TemplateResponse("configuration.html", context)


@app.get("/logs", response_class=HTMLResponse)
def logs(request: Request):
    r = require_login(request)
    if r:
        return r
    rows = get_events(limit=200)
    events = [dict(r) for r in rows]
    return templates.TemplateResponse(
        "status.html",
        {"request": request, "events": events, "user": request.session.get("user"), "active_page": "logs"},
    )


# --- CONFIGURATION: BINANCE SAVE/TEST ---
@app.post("/configuration/binance")
def save_binance_config(
    request: Request,
    binance_env: str = Form(...),
    binance_api_key: str = Form(...),
    binance_api_secret: str = Form(...),
):
    r = require_login(request)
    if r:
        return r

    user_email = request.session.get("user")
    if not user_email:
        return RedirectResponse(url="/login", status_code=303)

    if not binance_api_key.strip() or not binance_api_secret.strip():
        return RedirectResponse(url="/configuration?error=Missing+API+Key+or+Secret", status_code=303)

    upsert_user_profile_base(user_email=user_email, user_password_hash=AUTH_PASSWORD_HASH)

    try:
        update_binance_credentials(
            user_email=user_email,
            env=binance_env,
            api_key=binance_api_key.strip(),
            api_secret=binance_api_secret.strip(),
        )
        log_event(f"User {user_email} -> saved Binance credentials ({binance_env})", level="INFO")
        return RedirectResponse(url="/configuration?saved=Binance+saved", status_code=303)
    except Exception as e:
        log_event(f"User {user_email} -> Binance save failed: {e}", level="ERROR")
        return RedirectResponse(url="/configuration?error=Save+failed", status_code=303)


@app.post("/configuration/binance/test")
def test_binance_connection(request: Request, binance_env: str = Form(...)):
    r = require_login(request)
    if r:
        return r

    user_email = request.session.get("user")
    profile = _get_profile_dict(user_email)
    if not profile:
        return RedirectResponse(url="/configuration?error=No+user+profile+found", status_code=303)

    if binance_env == "testnet":
        api_key = (profile.get("testnetAPIKey") or "").strip()
        api_secret = (profile.get("testnetAPISecret") or "").strip()
        base = TESTNET_BASE
    else:
        api_key = (profile.get("mainnetAPIKey") or "").strip()
        api_secret = (profile.get("mainnetAPISecret") or "").strip()
        base = MAINNET_BASE

    if not api_key or not api_secret:
        return RedirectResponse(
            url="/configuration?error=Missing+API+Key+or+Secret+for+selected+environment",
            status_code=303,
        )

    try:
        _ = signed_get(base, "/v3/account", api_key, api_secret)
        log_event(f"User {user_email} -> Binance {binance_env} test connection OK", level="INFO")
        return RedirectResponse(url="/configuration?saved=Binance+test+connection+OK", status_code=303)
    except Exception as e:
        log_event(f"User {user_email} -> Binance {binance_env} test connection FAIL: {e}", level="ERROR")
        return RedirectResponse(url="/configuration?error=Binance+test+connection+FAILED", status_code=303)


# --- API: ACTIVE EXCHANGE ---
@app.get("/api/active-exchange", response_class=JSONResponse)
def api_get_active_exchange(request: Request):
    r = require_login(request)
    if r:
        return {"error": "not_logged_in"}

    user_email = request.session.get("user")
    profile = _get_profile_dict(user_email)

    items = build_configured_exchanges(profile)
    active = _get_active_exchange_id(request, items)

    return {"active": active, "items": items}


@app.post("/api/active-exchange", response_class=JSONResponse)
def api_set_active_exchange(request: Request, exchange_id: str = Form(...)):
    r = require_login(request)
    if r:
        return {"error": "not_logged_in"}

    user_email = request.session.get("user")
    profile = _get_profile_dict(user_email)
    items = build_configured_exchanges(profile)
    configured_ids = {i["id"] for i in items}

    if exchange_id not in configured_ids:
        return {"error": "invalid_exchange_id", "active": request.session.get("active_exchange_id")}

    request.session["active_exchange_id"] = exchange_id
    log_event(f"User {user_email} -> active exchange set: {exchange_id}", level="INFO")
    return {"ok": True, "active": exchange_id}


# --- API: UNIVERSAL BALANCES ---
@app.get("/api/balances", response_class=JSONResponse)
def api_balances(request: Request):
    r = require_login(request)
    if r:
        return {"error": "not_logged_in"}

    user_email = request.session.get("user")
    profile = _get_profile_dict(user_email)
    if not profile:
        return {"error": "no_profile"}

    items = build_configured_exchanges(profile)
    active_id = _get_active_exchange_id(request, items)

    ex, env = parse_exchange_id(active_id)
    if not ex or not env:
        return {"error": "no_active_exchange"}

    if ex == "binance":
        if env == "testnet":
            api_key = (profile.get("testnetAPIKey") or "").strip()
            api_secret = (profile.get("testnetAPISecret") or "").strip()
            base = TESTNET_BASE
        else:
            api_key = (profile.get("mainnetAPIKey") or "").strip()
            api_secret = (profile.get("mainnetAPISecret") or "").strip()
            base = MAINNET_BASE

        if not api_key or not api_secret:
            return {"error": "missing_keys", "exchange": ex, "env": env}

        try:
            acct = get_account(base, api_key, api_secret)
            balances = extract_balances(acct, min_free=0.0)
            balances = [b for b in balances if b.get("asset") in BINANCE_BALANCE_ASSETS]
            balances.sort(key=lambda x: x.get("asset") or "")
            return {"exchange": ex, "env": env, "exchange_id": active_id, "balances": balances}
        except Exception as e:
            log_event(f"User {user_email} -> Binance {env} balances FAIL: {e}", level="ERROR")
            return {"error": "fetch_failed", "exchange": ex, "env": env}

    if ex == "coinbase":
        return {"error": "not_implemented", "exchange": ex, "env": env, "exchange_id": active_id}

    return {"error": "unknown_exchange", "exchange": ex, "env": env, "exchange_id": active_id}


# --- API: BINANCE USER STREAM (listenKey -> DB) ---
@app.post("/api/binance/user-stream/start", response_class=JSONResponse)
def api_binance_user_stream_start(request: Request, env: str = "testnet"):
    r = require_login(request)
    if r:
        return {"error": "not_logged_in"}

    if env != "testnet":
        return {"error": "only_testnet_supported"}

    user_email = request.session.get("user")
    profile = _get_profile_dict(user_email)
    if not profile:
        return {"error": "no_profile"}

    api_key = (profile.get("testnetAPIKey") or "").strip()
    if not api_key:
        return {"error": "missing_api_key"}

    try:
        listen_key = start_user_stream(TESTNET_BASE, api_key)
        update_binance_listenkey(user_email, "testnet", listen_key)
        log_event(f"User {user_email} -> Binance testnet user stream started", level="INFO")
        return {"ok": True, "env": "testnet", "listenKeySaved": True}
    except Exception as e:
        log_event(f"User {user_email} -> Binance testnet user stream start FAIL: {e}", level="ERROR")
        return {"error": "start_failed"}


@app.post("/api/binance/user-stream/keepalive", response_class=JSONResponse)
def api_binance_user_stream_keepalive(request: Request, env: str = "testnet"):
    r = require_login(request)
    if r:
        return {"error": "not_logged_in"}

    if env != "testnet":
        return {"error": "only_testnet_supported"}

    user_email = request.session.get("user")
    profile = _get_profile_dict(user_email)
    if not profile:
        return {"error": "no_profile"}

    api_key = (profile.get("testnetAPIKey") or "").strip()
    listen_key = (profile.get("testnetListenKey") or "").strip()

    if not api_key or not listen_key:
        return {"error": "missing_api_key_or_listenkey"}

    try:
        keepalive_user_stream(TESTNET_BASE, api_key, listen_key)
        update_binance_listenkey(user_email, "testnet", listen_key)
        return {"ok": True, "env": "testnet"}
    except Exception as e:
        log_event(f"User {user_email} -> Binance testnet user stream keepalive FAIL: {e}", level="ERROR")
        return {"error": "keepalive_failed"}


# --- WS: BINANCE USER STREAM PROXY (testnet) ---
@app.websocket("/ws/binance/user-stream")
async def ws_binance_user_stream(websocket: WebSocket, env: str = "testnet"):
    import asyncio
    import traceback

    try:
        await websocket.accept()
        await websocket.send_json({"type": "hello", "msg": "ws accepted"})

        if env != "testnet":
            await websocket.send_json({"type": "error", "error": "only_testnet_supported"})
            await asyncio.sleep(0.05)
            await websocket.close(code=1008)
            return

        user_email = ws_get_user_email(websocket)
        if not user_email:
            await websocket.send_json({"type": "error", "error": "not_logged_in (no session on WS)"})
            await asyncio.sleep(0.05)
            await websocket.close(code=1008)
            return

        profile = _get_profile_dict(user_email)
        if not profile:
            await websocket.send_json({"type": "error", "error": "no_profile"})
            await asyncio.sleep(0.05)
            await websocket.close(code=1008)
            return

        listen_key = (profile.get("testnetListenKey") or "").strip()
        if not listen_key:
            await websocket.send_json({"type": "error", "error": "missing_listenkey"})
            await asyncio.sleep(0.05)
            await websocket.close(code=1008)
            return

        # ✅ Correct WS base for Spot Testnet streams
        # base: wss://stream.testnet.binance.vision/ws  (raw stream: /ws/<streamName>)
        upstream_url = f"wss://stream.testnet.binance.vision/ws/{listen_key}"

        await websocket.send_json(
            {"type": "status", "connected": False, "env": env, "phase": "connecting_upstream"}
        )

        async with websockets.connect(upstream_url, ping_interval=20, ping_timeout=20) as upstream:
            await websocket.send_json({"type": "status", "connected": True, "env": env, "phase": "connected"})

            while True:
                msg = await upstream.recv()
                try:
                    payload = json.loads(msg)
                except Exception:
                    payload = {"raw": msg}

                await websocket.send_json({"type": "binance_event", "env": env, "data": payload})

    except WebSocketDisconnect:
        return

    except Exception as e:
        err = f"{type(e).__name__}: {str(e)}"
        tb = traceback.format_exc()
        log_event(f"WS server error: {err}\n{tb}", level="ERROR")

        try:
            await websocket.send_json({"type": "error", "error": f"server_exception: {err}"})
            await asyncio.sleep(0.05)
            await websocket.close(code=1011)
        except Exception:
            pass


# --- API: PRICES (CoinMarketCap) ---
@app.get("/api/prices", response_class=JSONResponse)
def api_prices(request: Request):
    now = time.time()
    if _prices_cache["data"] and (now - _prices_cache["ts"] < PRICES_TTL_SECONDS):
        return _prices_cache["data"]

    if not CMC_API_KEY:
        log_event("Missing CMC_API_KEY in .env (ticker disabled)", level="WARNING")
        data = {
            "btc_usd": None,
            "eth_usd": None,
            "btc_24h": None,
            "eth_24h": None,
            "source": "coinmarketcap",
            "convert": CMC_CONVERT,
            "error": "missing_api_key",
        }
        _prices_cache.update({"ts": now, "data": data})
        return data

    headers = {"Accept": "application/json", "X-CMC_PRO_API_KEY": CMC_API_KEY}
    params = {"symbol": "BTC,ETH", "convert": CMC_CONVERT}

    try:
        with httpx.Client(timeout=4.0) as client:
            resp = client.get(CMC_URL, headers=headers, params=params)
            resp.raise_for_status()
            payload = resp.json()

        data_node = payload.get("data", {})
        btc_quote = data_node.get("BTC", {}).get("quote", {}).get(CMC_CONVERT, {})
        eth_quote = data_node.get("ETH", {}).get("quote", {}).get(CMC_CONVERT, {})

        result = {
            "btc_usd": float(btc_quote.get("price")) if btc_quote.get("price") is not None else None,
            "eth_usd": float(eth_quote.get("price")) if eth_quote.get("price") is not None else None,
            "btc_24h": float(btc_quote.get("percent_change_24h")) if btc_quote.get("percent_change_24h") is not None else None,
            "eth_24h": float(eth_quote.get("percent_change_24h")) if eth_quote.get("percent_change_24h") is not None else None,
            "source": "coinmarketcap",
            "convert": CMC_CONVERT,
        }

        _prices_cache.update({"ts": now, "data": result})
        return result

    except httpx.HTTPError as e:
        log_event(f"CMC price fetch failed (HTTP): {e}", level="ERROR")
    except Exception as e:
        log_event(f"CMC price fetch failed: {e}", level="ERROR")

    if _prices_cache["data"]:
        return _prices_cache["data"]

    return {
        "btc_usd": None,
        "eth_usd": None,
        "btc_24h": None,
        "eth_24h": None,
        "source": "coinmarketcap",
        "convert": CMC_CONVERT,
        "error": "fetch_failed",
    }