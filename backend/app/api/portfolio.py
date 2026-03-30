"""Portfolio API endpoints."""
import sqlite3
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.db.database import get_db
from app.market.cache import PriceCache

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


class TradeRequest(BaseModel):
    ticker: str
    quantity: float
    side: str  # "buy" or "sell"


def compute_total_value(conn: sqlite3.Connection, cache: PriceCache) -> float:
    """Compute total portfolio value: cash + sum of position market values."""
    profile = conn.execute(
        "SELECT cash_balance FROM users_profile WHERE id = 'default'"
    ).fetchone()
    cash = profile["cash_balance"] if profile else 0.0

    positions = conn.execute(
        "SELECT ticker, quantity FROM positions WHERE user_id = 'default'"
    ).fetchall()

    equity = sum(
        row["quantity"] * price
        for row in positions
        if (price := cache.get_price(row["ticker"])) is not None
    )
    return cash + equity


@router.get("")
def get_portfolio(request: Request):
    """Return current cash, positions, and total portfolio value."""
    cache = request.app.state.price_cache
    with get_db() as conn:
        profile = conn.execute(
            "SELECT cash_balance FROM users_profile WHERE id = 'default'"
        ).fetchone()
        cash = profile["cash_balance"] if profile else 0.0

        rows = conn.execute(
            "SELECT ticker, quantity, avg_cost FROM positions WHERE user_id = 'default'"
        ).fetchall()

    positions = []
    equity = 0.0
    for row in rows:
        ticker = row["ticker"]
        qty = row["quantity"]
        avg_cost = row["avg_cost"]
        current_price = cache.get_price(ticker)

        if current_price is not None:
            unrealized_pnl = (current_price - avg_cost) * qty
            pnl_percent = ((current_price - avg_cost) / avg_cost * 100) if avg_cost else 0.0
            equity += qty * current_price
        else:
            unrealized_pnl = 0.0
            pnl_percent = 0.0

        positions.append(
            {
                "ticker": ticker,
                "quantity": qty,
                "avg_cost": avg_cost,
                "current_price": current_price,
                "unrealized_pnl": round(unrealized_pnl, 2),
                "pnl_percent": round(pnl_percent, 2),
            }
        )

    return {
        "cash_balance": cash,
        "total_value": round(cash + equity, 2),
        "positions": positions,
    }


@router.post("/trade")
def execute_trade(body: TradeRequest, request: Request):
    """Execute a buy or sell market order."""
    cache = request.app.state.price_cache
    ticker = body.ticker.upper().strip()
    qty = body.quantity
    side = body.side.lower()

    price = cache.get_price(ticker)
    if price is None:
        raise HTTPException(status_code=400, detail=f"No price available for {ticker}")

    now = datetime.now(timezone.utc).isoformat()
    trade_id = str(uuid.uuid4())

    with get_db() as conn:
        if side == "buy":
            _execute_buy(conn, ticker, qty, price, now, trade_id)
        elif side == "sell":
            _execute_sell(conn, ticker, qty, price, now, trade_id)
        else:
            raise HTTPException(status_code=400, detail="side must be 'buy' or 'sell'")

        total = compute_total_value(conn, cache)
        conn.execute(
            "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at) VALUES (?, 'default', ?, ?)",
            (str(uuid.uuid4()), total, now),
        )

    return {
        "status": "ok",
        "trade": {
            "id": trade_id,
            "ticker": ticker,
            "side": side,
            "quantity": qty,
            "price": price,
            "executed_at": now,
        },
    }


def _execute_buy(
    conn: sqlite3.Connection, ticker: str, qty: float, price: float, now: str, trade_id: str
) -> None:
    profile = conn.execute(
        "SELECT cash_balance FROM users_profile WHERE id = 'default'"
    ).fetchone()
    cash = profile["cash_balance"]
    cost = qty * price

    if cash < cost:
        raise HTTPException(status_code=400, detail="Insufficient cash")

    conn.execute(
        "UPDATE users_profile SET cash_balance = ? WHERE id = 'default'",
        (cash - cost,),
    )

    existing = conn.execute(
        "SELECT quantity, avg_cost FROM positions WHERE user_id = 'default' AND ticker = ?",
        (ticker,),
    ).fetchone()

    if existing:
        new_qty = existing["quantity"] + qty
        new_avg = (existing["quantity"] * existing["avg_cost"] + qty * price) / new_qty
        conn.execute(
            "UPDATE positions SET quantity = ?, avg_cost = ?, updated_at = ? WHERE user_id = 'default' AND ticker = ?",
            (new_qty, new_avg, now, ticker),
        )
    else:
        conn.execute(
            "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at) VALUES (?, 'default', ?, ?, ?, ?)",
            (str(uuid.uuid4()), ticker, qty, price, now),
        )

    conn.execute(
        "INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at) VALUES (?, 'default', ?, 'buy', ?, ?, ?)",
        (trade_id, ticker, qty, price, now),
    )


def _execute_sell(
    conn: sqlite3.Connection, ticker: str, qty: float, price: float, now: str, trade_id: str
) -> None:
    existing = conn.execute(
        "SELECT quantity, avg_cost FROM positions WHERE user_id = 'default' AND ticker = ?",
        (ticker,),
    ).fetchone()

    if not existing or existing["quantity"] < qty:
        raise HTTPException(status_code=400, detail="Insufficient shares")

    profile = conn.execute(
        "SELECT cash_balance FROM users_profile WHERE id = 'default'"
    ).fetchone()
    conn.execute(
        "UPDATE users_profile SET cash_balance = ? WHERE id = 'default'",
        (profile["cash_balance"] + qty * price,),
    )

    new_qty = existing["quantity"] - qty
    if new_qty < 1e-9:
        conn.execute(
            "DELETE FROM positions WHERE user_id = 'default' AND ticker = ?", (ticker,)
        )
    else:
        conn.execute(
            "UPDATE positions SET quantity = ?, updated_at = ? WHERE user_id = 'default' AND ticker = ?",
            (new_qty, now, ticker),
        )

    conn.execute(
        "INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at) VALUES (?, 'default', ?, 'sell', ?, ?, ?)",
        (trade_id, ticker, qty, price, now),
    )


@router.get("/history")
def get_history():
    """Return portfolio value snapshots over time."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT total_value, recorded_at FROM portfolio_snapshots WHERE user_id = 'default' ORDER BY recorded_at"
        ).fetchall()
    return [{"total_value": r["total_value"], "recorded_at": r["recorded_at"]} for r in rows]
