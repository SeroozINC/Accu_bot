# app/connections/db_connections.py
import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent / "db_connections.sqlite"

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """
    Tworzy tabelę bot_events jeśli nie istnieje.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bot_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event TEXT NOT NULL,
        level TEXT DEFAULT 'INFO',
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.commit()
    conn.close()

def log_event(event: str, level: str = "INFO"):
    """
    Loguje event bota do bazy.
    
    Args:
        event (str): Treść eventu.
        level (str): Poziom eventu (INFO, WARNING, ERROR).
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO bot_events (event, level, timestamp) VALUES (?, ?, ?)",
        (event, level, datetime.utcnow())
    )
    conn.commit()
    conn.close()