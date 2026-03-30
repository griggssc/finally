"""SQLite database connection, initialization, and seeding."""
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

import os
DB_PATH = Path(os.environ.get("DB_PATH", "/app/db/finally.db"))
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

DEFAULT_WATCHLIST = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"]


def get_db() -> sqlite3.Connection:
    """Get a database connection with row_factory set."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """Create schema and seed default data if not already present."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_db() as conn:
        conn.executescript(SCHEMA_PATH.read_text())
        _seed_if_empty(conn)


def _seed_if_empty(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT id FROM users_profile WHERE id = 'default'").fetchone()
    if row:
        return
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO users_profile (id, cash_balance, created_at) VALUES ('default', 10000.0, ?)",
        (now,),
    )
    for ticker in DEFAULT_WATCHLIST:
        conn.execute(
            "INSERT OR IGNORE INTO watchlist (id, user_id, ticker, added_at) VALUES (?, 'default', ?, ?)",
            (str(uuid.uuid4()), ticker, now),
        )
