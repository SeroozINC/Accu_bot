# app/connections/db_connections.py
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional

DB_PATH = Path(__file__).parent / "db_connections.sqlite"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """
    Tworzy (lub aktualizuje) tabelę bot_events.
    Jeśli tabela istnieje w starszej wersji bez kolumny `level`,
    to doda kolumnę `level` przez ALTER TABLE.
    """
    conn = get_connection()
    cur = conn.cursor()

    # 1) Upewnij się, że tabela istnieje (minimalny zestaw kolumn)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS bot_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
        """
    )

    # 2) Jeśli brakuje kolumny `level`, dodaj ją (kompatybilność wstecz)
    cur.execute("PRAGMA table_info(bot_events)")
    columns = {row["name"] for row in cur.fetchall()}
    if "level" not in columns:
        cur.execute("ALTER TABLE bot_events ADD COLUMN level TEXT DEFAULT 'INFO'")

    conn.commit()
    conn.close()


def log_event(event: str, level: str = "INFO") -> None:
    """
    Loguje event bota do bazy.

    Args:
        event: Treść eventu.
        level: INFO / WARNING / ERROR (lub inne, jeśli zechcesz).
    """
    # ISO 8601 UTC, czytelne w DB Browser
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

    conn = get_connection()
    cur = conn.cursor()

    # W przypadku starej tabeli bez level, init_db() doda ją.
    # Jeśli ktoś zapomni wywołać init_db(), insert i tak zadziała, bo level ma DEFAULT po migracji.
    cur.execute(
        "INSERT INTO bot_events (event, level, timestamp) VALUES (?, ?, ?)",
        (event, level, ts),
    )

    conn.commit()
    conn.close()


def get_events(limit: int = 200) -> List[sqlite3.Row]:
    """
    Zwraca ostatnie eventy bota (od najnowszych).

    Args:
        limit: Ile rekordów zwrócić.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, event, level, timestamp
        FROM bot_events
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_events_since_id(last_id: int, limit: int = 200) -> List[sqlite3.Row]:
    """
    Przydatne do odświeżania UI: pobierz eventy nowsze niż last_id.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, event, level, timestamp
        FROM bot_events
        WHERE id > ?
        ORDER BY id ASC
        LIMIT ?
        """,
        (last_id, limit),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


if __name__ == "__main__":
    init_db()
    log_event("db_connections init test", level="INFO")
    for r in get_events(limit=5):
        print(dict(r))