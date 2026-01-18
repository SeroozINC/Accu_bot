# app/models/user_profile_db.py
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "UserProfile.sqlite"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _add_column_if_missing(conn: sqlite3.Connection, table: str, col: str, coldef: str) -> None:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    cols = {row[1] for row in cur.fetchall()}
    if col not in cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coldef}")
        conn.commit()


def init_userprofile_db() -> None:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS UserProfile (
            userEmail TEXT PRIMARY KEY,
            userPasswordHash TEXT,
            mainnetAPIKey TEXT,
            mainnetAPISecret TEXT,
            testnetAPIKey TEXT,
            testnetAPISecret TEXT,
            testnetListenKey TEXT,
            testnetListenKeyUpdated DATETIME,
            dateCreated DATETIME DEFAULT CURRENT_TIMESTAMP,
            dateUpdated DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()

    # Migrations / ensure columns exist for older DBs
    _add_column_if_missing(conn, "UserProfile", "userPasswordHash", "TEXT")
    _add_column_if_missing(conn, "UserProfile", "mainnetAPIKey", "TEXT")
    _add_column_if_missing(conn, "UserProfile", "mainnetAPISecret", "TEXT")
    _add_column_if_missing(conn, "UserProfile", "testnetAPIKey", "TEXT")
    _add_column_if_missing(conn, "UserProfile", "testnetAPISecret", "TEXT")
    _add_column_if_missing(conn, "UserProfile", "testnetListenKey", "TEXT")
    _add_column_if_missing(conn, "UserProfile", "testnetListenKeyUpdated", "DATETIME")
    _add_column_if_missing(conn, "UserProfile", "dateCreated", "DATETIME DEFAULT CURRENT_TIMESTAMP")
    _add_column_if_missing(conn, "UserProfile", "dateUpdated", "DATETIME DEFAULT CURRENT_TIMESTAMP")

    conn.close()


def get_user_profile(user_email: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM UserProfile WHERE userEmail = ?", (user_email,))
    row = cur.fetchone()
    conn.close()
    return row


def upsert_user_profile_base(user_email: str, user_password_hash: str | None = None) -> None:
    """
    Ensure the user exists.
    - If record exists -> update dateUpdated (+ optional password hash).
    - If not -> insert new record.
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT userEmail FROM UserProfile WHERE userEmail = ?", (user_email,))
    existing = cur.fetchone()

    if existing is None:
        cur.execute(
            """
            INSERT INTO UserProfile (userEmail, userPasswordHash)
            VALUES (?, ?)
            """,
            (user_email, user_password_hash),
        )
    else:
        if user_password_hash:
            cur.execute(
                """
                UPDATE UserProfile
                SET userPasswordHash = ?, dateUpdated = CURRENT_TIMESTAMP
                WHERE userEmail = ?
                """,
                (user_password_hash, user_email),
            )
        else:
            cur.execute(
                """
                UPDATE UserProfile
                SET dateUpdated = CURRENT_TIMESTAMP
                WHERE userEmail = ?
                """,
                (user_email,),
            )

    conn.commit()
    conn.close()


def update_binance_credentials(user_email: str, env: str, api_key: str, api_secret: str) -> None:
    """
    env: 'mainnet' or 'testnet'
    Stores credentials in the corresponding columns.
    """
    if env not in ("mainnet", "testnet"):
        raise ValueError("env must be 'mainnet' or 'testnet'")

    conn = get_connection()
    cur = conn.cursor()

    # ensure record exists
    cur.execute("SELECT userEmail FROM UserProfile WHERE userEmail = ?", (user_email,))
    exists = cur.fetchone()

    if not exists:
        cur.execute("INSERT INTO UserProfile (userEmail) VALUES (?)", (user_email,))

    if env == "mainnet":
        cur.execute(
            """
            UPDATE UserProfile
            SET mainnetAPIKey = ?, mainnetAPISecret = ?, dateUpdated = CURRENT_TIMESTAMP
            WHERE userEmail = ?
            """,
            (api_key, api_secret, user_email),
        )
    else:
        cur.execute(
            """
            UPDATE UserProfile
            SET testnetAPIKey = ?, testnetAPISecret = ?, dateUpdated = CURRENT_TIMESTAMP
            WHERE userEmail = ?
            """,
            (api_key, api_secret, user_email),
        )

    conn.commit()
    conn.close()


def update_binance_listenkey(user_email: str, env: str, listen_key: str) -> None:
    """
    Save (or refresh timestamp for) Binance listenKey for the given env.
    For now we support testnet. Mainnet can be added later similarly.
    """
    if env not in ("testnet", "mainnet"):
        raise ValueError("env must be 'testnet' or 'mainnet'")

    conn = get_connection()
    cur = conn.cursor()

    # ensure record exists
    cur.execute("SELECT userEmail FROM UserProfile WHERE userEmail = ?", (user_email,))
    exists = cur.fetchone()
    if not exists:
        cur.execute("INSERT INTO UserProfile (userEmail) VALUES (?)", (user_email,))

    if env == "testnet":
        cur.execute(
            """
            UPDATE UserProfile
            SET testnetListenKey = ?,
                testnetListenKeyUpdated = CURRENT_TIMESTAMP,
                dateUpdated = CURRENT_TIMESTAMP
            WHERE userEmail = ?
            """,
            (listen_key, user_email),
        )
    else:
        # leave as not implemented for now, but structure supports it
        cur.execute(
            """
            UPDATE UserProfile
            SET dateUpdated = CURRENT_TIMESTAMP
            WHERE userEmail = ?
            """,
            (user_email,),
        )
        raise NotImplementedError("Mainnet listenKey storage not implemented yet")

    conn.commit()
    conn.close()