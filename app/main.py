import os
import time

import httpx
from dotenv import load_dotenv
from passlib.context import CryptContext
from starlette.middleware.sessions import SessionMiddleware

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.connections.db_connections import init_db, log_event, get_events
from app.connections.connections import connect_binance, connect_coinbase


# --- ENV / CONFIG ---
load_dotenv()

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

SESSION_SECRET = os.getenv("SESSION_SECRET", "")
AUTH_USERNAME = os.getenv("ADMIN_USERNAME", "")
AUTH_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH", "")

CMC_API_KEY = os.getenv("CMC_API_KEY", "")
CMC_CONVERT = os.getenv("CMC_CONVERT", "USD")
CMC_URL = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"

# Cache cen (żeby nie zjadać limitów CoinMarketCap)
_prices_cache = {"ts": 0.0, "data": None}
PRICES_TTL_SECONDS = 10

if not SESSION_SECRET:
    raise RuntimeError("Brak SESSION_SECRET w .env")
if not AUTH_USERNAME or not AUTH_PASSWORD_HASH:
    raise RuntimeError("Brak ADMIN_USERNAME lub ADMIN_PASSWORD_HASH w .env")


# --- APP SETUP ---
app = FastAPI()

templates = Jinja2Templates(directory="ui/templates")
app.mount("/static", StaticFiles(directory="ui/static"), name="static")

app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)


# --- AUTH HELPERS ---
def is_logged_in(request: Request) -> bool:
    return bool(request.session.get("user"))


def require_login(request: Request):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=303)
    return None


# --- LIFECYCLE ---
@app.on_event("startup")
def on_startup():
    init_db()
    log_event("Bot start", level="INFO")


# --- ROUTES: AUTH ---
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if is_logged_in(request):
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": None, "user": None},
    )


@app.post("/login", response_class=HTMLResponse)
def login_action(request: Request, username: str = Form(...), password: str = Form(...)):
    if username == AUTH_USERNAME and pwd_context.verify(password, AUTH_PASSWORD_HASH):
        request.session["user"] = username
        log_event(f"Login success: {username}", level="INFO")
        return RedirectResponse(url="/", status_code=303)

    log_event(f"Login failed: {username}", level="WARNING")
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": "Błędny login lub hasło", "user": None},
    )


@app.post("/logout")
def logout(request: Request):
    user = request.session.get("user")
    request.session.clear()
    if user:
        log_event(f"Logout: {user}", level="INFO")
    return RedirectResponse(url="/login", status_code=303)


# --- ROUTES: UI ---
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    r = require_login(request)
    if r:
        return r
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "user": request.session.get("user")},
    )


@app.get("/status", response_class=HTMLResponse)
def status(request: Request):
    r = require_login(request)
    if r:
        return r
    rows = get_events(limit=200)
    events = [dict(r) for r in rows]
    return templates.TemplateResponse(
        "status.html",
        {"request": request, "events": events, "user": request.session.get("user")},
    )


# --- ROUTES: PRICES API (CoinMarketCap) ---
@app.get("/api/prices", response_class=JSONResponse)
def api_prices(request: Request):
    now = time.time()

    # cache hit
    if _prices_cache["data"] and (now - _prices_cache["ts"] < PRICES_TTL_SECONDS):
        return _prices_cache["data"]

    if not CMC_API_KEY:
        log_event("Brak CMC_API_KEY w .env (ticker cen nie działa)", level="WARNING")
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

    headers = {
        "Accept": "application/json",
        "X-CMC_PRO_API_KEY": CMC_API_KEY,
    }
    params = {
        "symbol": "BTC,ETH",
        "convert": CMC_CONVERT,
    }

    try:
        with httpx.Client(timeout=4.0) as client:
            resp = client.get(CMC_URL, headers=headers, params=params)
            resp.raise_for_status()
            payload = resp.json()

        data_node = payload.get("data", {})

        btc_quote = data_node.get("BTC", {}).get("quote", {}).get(CMC_CONVERT, {})
        eth_quote = data_node.get("ETH", {}).get("quote", {}).get(CMC_CONVERT, {})

        btc_price = btc_quote.get("price")
        eth_price = eth_quote.get("price")

        btc_24h = btc_quote.get("percent_change_24h")
        eth_24h = eth_quote.get("percent_change_24h")

        result = {
            "btc_usd": float(btc_price) if btc_price is not None else None,
            "eth_usd": float(eth_price) if eth_price is not None else None,
            "btc_24h": float(btc_24h) if btc_24h is not None else None,
            "eth_24h": float(eth_24h) if eth_24h is not None else None,
            "source": "coinmarketcap",
            "convert": CMC_CONVERT,
        }

        _prices_cache.update({"ts": now, "data": result})
        return result

    except httpx.HTTPError as e:
        log_event(f"CMC price fetch failed (HTTP): {e}", level="ERROR")
    except Exception as e:
        log_event(f"CMC price fetch failed: {e}", level="ERROR")

    # fallback: jeśli CMC padnie, zwróć ostatni cache jeśli istnieje
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


# --- ROUTES: CONNECT (mock) ---
@app.post("/connect", response_class=HTMLResponse)
def connect(request: Request, exchange: str = Form(...)):
    r = require_login(request)
    if r:
        return r

    user = request.session.get("user")

    if exchange == "binance":
        ok = connect_binance()
        log_event(
            f"User {user} -> connect Binance: {'OK' if ok else 'FAIL'}",
            level="INFO" if ok else "ERROR",
        )
    elif exchange == "coinbase":
        ok = connect_coinbase()
        log_event(
            f"User {user} -> connect Coinbase: {'OK' if ok else 'FAIL'}",
            level="INFO" if ok else "ERROR",
        )
    else:
        log_event(f"Unknown exchange requested: {exchange}", level="WARNING")

    rows = get_events(limit=200)
    events = [dict(r) for r in rows]
    return templates.TemplateResponse(
        "status.html",
        {"request": request, "events": events, "user": user},
    )