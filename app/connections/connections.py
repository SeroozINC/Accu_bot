# app/connections/connections.py
from .db_connections import log_event

# Mockowe połączenia do giełd (na start bez API keys)

def connect_binance():
    try:
        log_event("Próba połączenia z Binance")
        # tutaj normalnie: klient = Client(API_KEY, API_SECRET)
        return True
    except Exception as e:
        log_event(f"Utrata połączenia z Binance: {e}")
        return False

def connect_coinbase():
    try:
        log_event("Próba połączenia z Coinbase")
        # tutaj normalnie: client = CoinbaseAdvancedTradeClient(API_KEY, API_SECRET)
        return True
    except Exception as e:
        log_event(f"Utrata połączenia z Coinbase: {e}")
        return False