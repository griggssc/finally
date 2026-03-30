"""Unit tests for watchlist operations."""
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest


def make_db() -> sqlite3.Connection:
    schema = (Path(__file__).parents[1] / "app/db/schema.sql").read_text()
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(schema)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO users_profile (id, cash_balance, created_at) VALUES ('default', 10000.0, ?)",
        (now,),
    )
    conn.commit()
    return conn


def add_ticker(conn, ticker):
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, 'default', ?, ?)",
        (str(uuid.uuid4()), ticker.upper(), now),
    )
    conn.commit()


def get_tickers(conn):
    rows = conn.execute(
        "SELECT ticker FROM watchlist WHERE user_id = 'default' ORDER BY added_at"
    ).fetchall()
    return [r["ticker"] for r in rows]


class TestWatchlist:
    def test_add_ticker(self):
        conn = make_db()
        add_ticker(conn, "AAPL")
        assert "AAPL" in get_tickers(conn)

    def test_add_duplicate_raises(self):
        conn = make_db()
        add_ticker(conn, "AAPL")
        with pytest.raises(sqlite3.IntegrityError):
            add_ticker(conn, "AAPL")

    def test_remove_ticker(self):
        conn = make_db()
        add_ticker(conn, "AAPL")
        add_ticker(conn, "MSFT")
        conn.execute(
            "DELETE FROM watchlist WHERE user_id = 'default' AND ticker = 'AAPL'"
        )
        conn.commit()
        tickers = get_tickers(conn)
        assert "AAPL" not in tickers
        assert "MSFT" in tickers

    def test_list_all_tickers(self):
        conn = make_db()
        for t in ["AAPL", "GOOGL", "MSFT"]:
            add_ticker(conn, t)
        tickers = get_tickers(conn)
        assert tickers == ["AAPL", "GOOGL", "MSFT"]
