"""Unit tests for portfolio trade execution logic."""
import sqlite3
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.market.cache import PriceCache


def make_db() -> sqlite3.Connection:
    """Create an in-memory SQLite DB with schema and seeded user."""
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


def make_cache(prices: dict[str, float]) -> PriceCache:
    cache = PriceCache()
    for ticker, price in prices.items():
        cache.update(ticker, price)
    return cache


def execute_buy(conn, cache, ticker, qty):
    from app.api.portfolio import _execute_buy
    price = cache.get_price(ticker)
    now = datetime.now(timezone.utc).isoformat()
    trade_id = str(uuid.uuid4())
    _execute_buy(conn, ticker, qty, price, now, trade_id)
    conn.commit()


def execute_sell(conn, cache, ticker, qty):
    from app.api.portfolio import _execute_sell
    price = cache.get_price(ticker)
    now = datetime.now(timezone.utc).isoformat()
    trade_id = str(uuid.uuid4())
    _execute_sell(conn, ticker, qty, price, now, trade_id)
    conn.commit()


def get_cash(conn):
    return conn.execute("SELECT cash_balance FROM users_profile WHERE id = 'default'").fetchone()["cash_balance"]


def get_position(conn, ticker):
    return conn.execute(
        "SELECT quantity, avg_cost FROM positions WHERE user_id = 'default' AND ticker = ?",
        (ticker,),
    ).fetchone()


class TestBuy:
    def test_buy_succeeds_and_deducts_cash(self):
        conn = make_db()
        cache = make_cache({"AAPL": 100.0})
        execute_buy(conn, cache, "AAPL", 10)
        assert get_cash(conn) == pytest.approx(9000.0)
        pos = get_position(conn, "AAPL")
        assert pos["quantity"] == 10
        assert pos["avg_cost"] == pytest.approx(100.0)

    def test_buy_insufficient_cash_raises(self):
        from fastapi import HTTPException
        conn = make_db()
        cache = make_cache({"AAPL": 100.0})
        with pytest.raises(HTTPException) as exc:
            execute_buy(conn, cache, "AAPL", 200)  # 20000 > 10000
        assert exc.value.status_code == 400
        assert "cash" in exc.value.detail.lower()

    def test_buy_recalculates_avg_cost(self):
        conn = make_db()
        cache = make_cache({"AAPL": 100.0})
        execute_buy(conn, cache, "AAPL", 10)  # 10 @ $100
        cache.update("AAPL", 120.0)
        execute_buy(conn, cache, "AAPL", 10)  # 10 @ $120
        pos = get_position(conn, "AAPL")
        assert pos["quantity"] == 20
        assert pos["avg_cost"] == pytest.approx(110.0)


class TestSell:
    def test_sell_succeeds_and_adds_cash(self):
        conn = make_db()
        cache = make_cache({"AAPL": 100.0})
        execute_buy(conn, cache, "AAPL", 10)
        cash_after_buy = get_cash(conn)
        cache.update("AAPL", 110.0)
        execute_sell(conn, cache, "AAPL", 5)
        assert get_cash(conn) == pytest.approx(cash_after_buy + 550.0)
        pos = get_position(conn, "AAPL")
        assert pos["quantity"] == 5

    def test_sell_removes_position_when_fully_sold(self):
        conn = make_db()
        cache = make_cache({"AAPL": 100.0})
        execute_buy(conn, cache, "AAPL", 10)
        execute_sell(conn, cache, "AAPL", 10)
        assert get_position(conn, "AAPL") is None

    def test_sell_insufficient_shares_raises(self):
        from fastapi import HTTPException
        conn = make_db()
        cache = make_cache({"AAPL": 100.0})
        execute_buy(conn, cache, "AAPL", 5)
        with pytest.raises(HTTPException) as exc:
            execute_sell(conn, cache, "AAPL", 10)
        assert exc.value.status_code == 400
        assert "shares" in exc.value.detail.lower()

    def test_sell_with_no_position_raises(self):
        from fastapi import HTTPException
        conn = make_db()
        cache = make_cache({"AAPL": 100.0})
        with pytest.raises(HTTPException):
            execute_sell(conn, cache, "AAPL", 1)


class TestPnL:
    def test_pnl_calculation(self):
        from app.api.portfolio import compute_total_value
        conn = make_db()
        cache = make_cache({"AAPL": 100.0})
        execute_buy(conn, cache, "AAPL", 10)
        cache.update("AAPL", 150.0)  # now worth $1500
        total = compute_total_value(conn, cache)
        # cash = 9000 + position value = 1500 = 10500
        assert total == pytest.approx(10500.0)
