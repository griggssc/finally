"""FastAPI application entry point."""
import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

load_dotenv(Path(__file__).parents[2] / ".env")

from app.db.database import get_db, init_db
from app.market.cache import PriceCache
from app.market.factory import create_market_data_source
from app.market.stream import create_stream_router
from app.api.health import router as health_router
from app.api.watchlist import router as watchlist_router
from app.api.portfolio import router as portfolio_router
from app.api.chat import router as chat_router

price_cache = PriceCache()


async def _portfolio_snapshot_task(app: FastAPI) -> None:
    """Record portfolio value every 30 seconds."""
    while True:
        await asyncio.sleep(30)
        try:
            from app.api.portfolio import compute_total_value
            with get_db() as conn:
                total = compute_total_value(conn, app.state.price_cache)
                conn.execute(
                    "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at) VALUES (?, 'default', ?, ?)",
                    (str(uuid.uuid4()), total, datetime.now(timezone.utc).isoformat()),
                )
        except Exception:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    with get_db() as conn:
        rows = conn.execute(
            "SELECT ticker FROM watchlist WHERE user_id = 'default'"
        ).fetchall()
        tickers = [r["ticker"] for r in rows]

    market_source = create_market_data_source(price_cache)
    await market_source.start(tickers)

    app.state.price_cache = price_cache
    app.state.market_source = market_source

    snapshot_task = asyncio.create_task(_portfolio_snapshot_task(app))

    yield

    snapshot_task.cancel()
    await market_source.stop()


app = FastAPI(lifespan=lifespan)

app.include_router(health_router)
app.include_router(create_stream_router(price_cache))
app.include_router(watchlist_router)
app.include_router(portfolio_router)
app.include_router(chat_router)

static_path = Path(os.environ.get("STATIC_PATH", "/app/static"))
if static_path.exists():
    app.mount("/", StaticFiles(directory=str(static_path), html=True), name="static")
