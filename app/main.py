# app/main.py
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.connections.db_connections import init_db, log_event, get_events
from app.connections.connections import connect_binance, connect_coinbase

app = FastAPI()

# Ścieżka do szablonów HTML
templates = Jinja2Templates(directory="ui/templates")

# Podłącz statyczne pliki jeśli będą w ui/static
app.mount("/static", StaticFiles(directory="ui/static"), name="static")


# ✅ Startup event - wykonuje się tylko raz przy starcie serwera
@app.on_event("startup")
def on_startup():
    init_db()
    log_event("Bot start", level="INFO")


# Strona główna
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# Endpoint łączący z giełdą
@app.post("/connect", response_class=HTMLResponse)
def connect(request: Request, exchange: str = Form(...)):
    if exchange == "binance":
        ok = connect_binance()
        log_event(
            "Połączono z Binance" if ok else "Błąd połączenia z Binance",
            level="INFO" if ok else "ERROR",
        )
    elif exchange == "coinbase":
        ok = connect_coinbase()
        log_event(
            "Połączono z Coinbase" if ok else "Błąd połączenia z Coinbase",
            level="INFO" if ok else "ERROR",
        )
    else:
        log_event(f"Nieznana giełda: {exchange}", level="WARNING")

    # Pobranie ostatnich logów z bazy (SQLite) i konwersja do dict dla Jinja
    rows = get_events(limit=200)
    events = [dict(r) for r in rows]

    return templates.TemplateResponse(
        "status.html",
        {"request": request, "events": events},
    )


# Uruchamianie lokalne
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )