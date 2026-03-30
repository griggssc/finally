"""Watchlist API endpoints."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.db.database import get_db

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


class AddTickerRequest(BaseModel):
    ticker: str


@router.get("")
def get_watchlist(request: Request):
    """Return all watched tickers with latest prices."""
    cache = request.app.state.price_cache
    with get_db() as conn:
        rows = conn.execute(
            "SELECT ticker FROM watchlist WHERE user_id = 'default' ORDER BY added_at"
        ).fetchall()

    result = []
    for row in rows:
        ticker = row["ticker"]
        update = cache.get(ticker)
        result.append(
            {
                "ticker": ticker,
                "price": update.price if update else None,
                "change": update.change if update else None,
                "change_percent": update.change_percent if update else None,
                "direction": update.direction if update else None,
            }
        )
    return result


@router.post("")
async def add_ticker(body: AddTickerRequest, request: Request):
    """Add a ticker to the watchlist."""
    ticker = body.ticker.upper().strip()
    now = datetime.now(timezone.utc).isoformat()

    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM watchlist WHERE user_id = 'default' AND ticker = ?", (ticker,)
        ).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail=f"{ticker} already in watchlist")

        entry_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, 'default', ?, ?)",
            (entry_id, ticker, now),
        )

    market_source = request.app.state.market_source
    if market_source:
        await market_source.add_ticker(ticker)

    return {"id": entry_id, "ticker": ticker, "added_at": now}


@router.delete("/{ticker}")
async def remove_ticker(ticker: str, request: Request):
    """Remove a ticker from the watchlist."""
    ticker = ticker.upper()

    with get_db() as conn:
        conn.execute(
            "DELETE FROM watchlist WHERE user_id = 'default' AND ticker = ?", (ticker,)
        )

    market_source = request.app.state.market_source
    if market_source:
        await market_source.remove_ticker(ticker)

    return None
