# app/main.py
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.connections.db_connections import init_db, log_event
from app.connections.connections import connect_binance, connect_coinbase
from app.logs.db_trades import log_trade
from app.db import SessionLocal, BotEvent  # jeśli potrzebujesz logów SQLAlchemy

app = FastAPI()

# Ścieżka do szablonów HTML
templates = Jinja2Templates(directory="ui/templates")

# Podłącz statyczne pliki jeśli będą w ui/static
app.mount("/static", StaticFiles(directory="ui/static"), name="static")

# ✅ Startup event - wykonuje się tylko raz przy starcie serwera
@app.on_event("startup")
def on_startup():
    # Inicjalizacja bazy eventów
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
        if ok:
            log_event("Połączono z Binance", level="INFO")
        else:
            log_event("Błąd połączenia z Binance", level="ERROR")
    else:
        ok = connect_coinbase()
        if ok:
            log_event("Połączono z Coinbase", level="INFO")
        else:
            log_event("Błąd połączenia z Coinbase", level="ERROR")

    # Pobranie ostatnich logów z bazy
    session = SessionLocal()
    events = session.query(BotEvent).order_by(BotEvent.id.desc()).all()
    session.close()

    return templates.TemplateResponse("status.html", {"request": request, "events": events})

# Uruchamianie lokalne
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True
    )