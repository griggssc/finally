"""Chat API endpoint with LLM integration and auto-trade execution."""
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.db.database import get_db
from app.llm.client import build_portfolio_context, call_llm

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str


@router.post("")
async def chat(body: ChatRequest, request: Request):
    """Send a message to the AI assistant, auto-execute any requested trades."""
    cache = request.app.state.price_cache
    now = datetime.now(timezone.utc).isoformat()

    # Build portfolio context
    from app.api.portfolio import get_portfolio
    from app.api.watchlist import get_watchlist
    portfolio = get_portfolio(request)
    watchlist = get_watchlist(request)

    # Load recent conversation history
    with get_db() as conn:
        rows = conn.execute(
            "SELECT role, content FROM chat_messages WHERE user_id = 'default' ORDER BY created_at DESC LIMIT 20"
        ).fetchall()
    history = [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    portfolio_context = build_portfolio_context(portfolio, watchlist)

    # Call LLM (may raise on timeout)
    try:
        llm_response = call_llm(portfolio_context, history, body.message)
    except Exception as exc:
        raise HTTPException(status_code=504, detail=f"LLM call failed: {exc}") from exc

    # Auto-execute trades
    executed_trades = []
    for trade in llm_response.trades:
        result = _try_execute_trade(cache, trade.ticker, trade.side, trade.quantity)
        executed_trades.append(result)

    # Auto-execute watchlist changes
    executed_watchlist = []
    for change in llm_response.watchlist_changes:
        result = await _try_watchlist_change(request, change.ticker, change.action)
        executed_watchlist.append(result)

    actions = {
        "trades": executed_trades,
        "watchlist_changes": executed_watchlist,
    }

    # Persist messages
    with get_db() as conn:
        conn.execute(
            "INSERT INTO chat_messages (id, user_id, role, content, actions, created_at) VALUES (?, 'default', 'user', ?, NULL, ?)",
            (str(uuid.uuid4()), body.message, now),
        )
        conn.execute(
            "INSERT INTO chat_messages (id, user_id, role, content, actions, created_at) VALUES (?, 'default', 'assistant', ?, ?, ?)",
            (str(uuid.uuid4()), llm_response.message, json.dumps(actions), now),
        )

    return {
        "message": llm_response.message,
        "trades": executed_trades,
        "watchlist_changes": executed_watchlist,
    }


def _try_execute_trade(cache, ticker: str, side: str, quantity: float) -> dict:
    """Attempt to execute a trade; return result with status."""
    from app.db.database import get_db
    from app.api.portfolio import _execute_buy, _execute_sell, compute_total_value
    import uuid
    from datetime import datetime, timezone

    ticker = ticker.upper()
    price = cache.get_price(ticker)

    if price is None:
        return {"ticker": ticker, "side": side, "quantity": quantity, "status": "failed", "error": f"No price for {ticker}"}

    now = datetime.now(timezone.utc).isoformat()
    trade_id = str(uuid.uuid4())

    try:
        with get_db() as conn:
            if side == "buy":
                _execute_buy(conn, ticker, quantity, price, now, trade_id)
            else:
                _execute_sell(conn, ticker, quantity, price, now, trade_id)
            total = compute_total_value(conn, cache)
            conn.execute(
                "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at) VALUES (?, 'default', ?, ?)",
                (str(uuid.uuid4()), total, now),
            )
        return {"ticker": ticker, "side": side, "quantity": quantity, "price": price, "status": "executed"}
    except Exception as exc:
        return {"ticker": ticker, "side": side, "quantity": quantity, "status": "failed", "error": str(exc)}


async def _try_watchlist_change(request: Request, ticker: str, action: str) -> dict:
    """Attempt a watchlist add/remove; return result with status."""
    ticker = ticker.upper()
    try:
        if action == "add":
            from app.api.watchlist import add_ticker, AddTickerRequest
            await add_ticker(AddTickerRequest(ticker=ticker), request)
        elif action == "remove":
            from app.api.watchlist import remove_ticker
            await remove_ticker(ticker, request)
        return {"ticker": ticker, "action": action, "status": "executed"}
    except Exception as exc:
        return {"ticker": ticker, "action": action, "status": "failed", "error": str(exc)}
