# app/main.py
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.connections.connections import connect_binance, connect_coinbase
from app.connections.db_connections import init_db, log_event, get_connection

app = FastAPI()
templates = Jinja2Templates(directory="ui/templates")

# Inicjalizacja bazy i log startowy
init_db()
log_event("Bot start")

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/connect", response_class=HTMLResponse)
def connect(request: Request, exchange: str = Form(...)):
    if exchange == "binance":
        ok = connect_binance()
        if ok:
            log_event("Połączono z Binance")
        else:
            log_event("Błąd połączenia z Binance")
    elif exchange == "coinbase":
        ok = connect_coinbase()
        if ok:
            log_event("Połączono z Coinbase")
        else:
            log_event("Błąd połączenia z Coinbase")

    # Pobranie logów z bazy
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM bot_events ORDER BY id DESC")
    events = cursor.fetchall()
    conn.close()

    return templates.TemplateResponse("status.html", {"request": request, "events": events})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True
    )