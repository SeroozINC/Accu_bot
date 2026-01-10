from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from db import init_db, log_event, SessionLocal, BotEvent
from connections import connect_binance, connect_coinbase

app = FastAPI()
templates = Jinja2Templates(directory="templates")

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
    else:
        ok = connect_coinbase()
        if ok:
            log_event("Połączono z Coinbase")
        else:
            log_event("Błąd połączenia z Coinbase")

    # Pobieramy logi
    session = SessionLocal()
    events = session.query(BotEvent).order_by(BotEvent.id.desc()).all()
    session.close()

    return templates.TemplateResponse("status.html", {"request": request, "events": events})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True
    )

