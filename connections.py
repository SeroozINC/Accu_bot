from db import log_event

# Możesz użyć prawdziwych SDK, ale na start robimy mocki,
# żeby bot działał bez API keys.

def connect_binance():
    try:
        log_event("Próba połączenia z Binance")
        # tutaj normalnie: klient = Client(API_KEY, API_SECRET)
        return True
    except:
        log_event("Utrata połączenia z Binance")
        return False

def connect_coinbase():
    try:
        log_event("Próba połączenia z Coinbase")
        # tutaj normalnie: client = CoinbaseAdvancedTradeClient(API_KEY, API_SECRET)
        return True
    except:
        log_event("Utrata połączenia z Coinbase")
        return False
