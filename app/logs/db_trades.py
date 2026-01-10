# app/logs/db_trades.py
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "db_trades.sqlite"

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT,
        side TEXT,
        price REAL,
        qty REAL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.commit()
    conn.close()

def log_trade(symbol, side, price, qty):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO trades (symbol, side, price, qty) VALUES (?, ?, ?, ?)",
        (symbol, side, price, qty)
    )
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()