# app/connections/db_connections.py
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "db_connections.sqlite"

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bot_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.commit()
    conn.close()

def log_event(event: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO bot_events (event) VALUES (?)", (event,))
    conn.commit()
    conn.close()

# Wywołaj init przy starcie
if __name__ == "__main__":
    init_db()