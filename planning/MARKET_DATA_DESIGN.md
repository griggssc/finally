# Market Data Design

Complete implementation guide for `backend/app/market/`. Covers every file with full code snippets.

---

## File Map

```
backend/app/market/
├── __init__.py
├── interface.py       # MarketDataSource ABC
├── models.py          # PriceUpdate frozen dataclass
├── cache.py           # PriceCache — shared in-memory state
├── seed_prices.py     # Starting prices and GBM params for known tickers
├── simulator.py       # GBMSimulator (pure math) + SimulatorDataSource (asyncio)
├── massive_client.py  # MassiveDataSource — polls Massive REST API
├── factory.py         # create_market_data_source() — env-driven selection
└── stream.py          # SSE router — GET /api/stream/prices
```

---

## `models.py`

Defines `PriceUpdate`, the single data shape passed through the entire market data pipeline.

```python
# backend/app/market/models.py
from __future__ import annotations
import time
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PriceUpdate:
    ticker: str
    price: float
    previous_price: float
    timestamp: float = field(default_factory=time.time)

    @property
    def change(self) -> float:
        return round(self.price - self.previous_price, 4)

    @property
    def change_percent(self) -> float:
        if self.previous_price == 0:
            return 0.0
        return round((self.price - self.previous_price) / self.previous_price * 100, 4)

    @property
    def direction(self) -> str:
        if self.price > self.previous_price:
            return "up"
        if self.price < self.previous_price:
            return "down"
        return "flat"

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "price": self.price,
            "previous_price": self.previous_price,
            "timestamp": self.timestamp,
            "change": self.change,
            "change_percent": self.change_percent,
            "direction": self.direction,
        }
```

**SSE payload example** (what the client receives per ticker):

```json
{
  "ticker": "AAPL",
  "price": 191.50,
  "previous_price": 191.30,
  "timestamp": 1743200000.123,
  "change": 0.2,
  "change_percent": 0.1045,
  "direction": "up"
}
```

---

## `cache.py`

Thread-safe in-memory store. The market data source writes to it; SSE streaming, portfolio valuation, and trade execution read from it.

```python
# backend/app/market/cache.py
from __future__ import annotations
import threading
import time
from app.market.models import PriceUpdate


class PriceCache:
    """
    Thread-safe in-memory price cache. Decouples data producers (simulator,
    Massive poller) from consumers (SSE stream, portfolio endpoints, trade execution).

    version increments on every update — SSE generator uses it to detect
    whether the cache has changed since the last push.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, PriceUpdate] = {}
        self._version: int = 0

    @property
    def version(self) -> int:
        return self._version

    def update(self, ticker: str, price: float, timestamp: float | None = None) -> None:
        """Write a new price. Derives previous_price from the current cached value."""
        with self._lock:
            existing = self._data.get(ticker)
            previous = existing.price if existing else price
            self._data[ticker] = PriceUpdate(
                ticker=ticker,
                price=round(price, 2),
                previous_price=round(previous, 2),
                timestamp=timestamp if timestamp is not None else time.time(),
            )
            self._version += 1

    def get(self, ticker: str) -> PriceUpdate | None:
        with self._lock:
            return self._data.get(ticker)

    def get_price(self, ticker: str) -> float | None:
        entry = self.get(ticker)
        return entry.price if entry else None

    def get_all(self) -> dict[str, PriceUpdate]:
        """Return a shallow copy — safe to iterate outside the lock."""
        with self._lock:
            return dict(self._data)

    def remove(self, ticker: str) -> None:
        with self._lock:
            self._data.pop(ticker, None)
            self._version += 1
```

**Usage pattern throughout the codebase:**

```python
# In trade execution endpoint — get current price for market order fill
price = price_cache.get_price("AAPL")
if price is None:
    raise HTTPException(404, "No price data for AAPL")

# In portfolio valuation — value all positions at current market
all_prices = price_cache.get_all()
for position in positions:
    current = all_prices.get(position.ticker)
    market_value = position.quantity * current.price if current else 0.0
```

---

## `interface.py`

Abstract base class that both data sources implement. All downstream code is typed against this — it never imports `SimulatorDataSource` or `MassiveDataSource` directly.

```python
# backend/app/market/interface.py
from __future__ import annotations
from abc import ABC, abstractmethod


class MarketDataSource(ABC):

    @abstractmethod
    async def start(self, tickers: list[str]) -> None:
        """
        Begin producing price updates. Spawns a background asyncio task.
        Seeds the cache immediately so consumers have data before the first tick.
        """
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Cancel the background task. Safe to call multiple times."""
        ...

    @abstractmethod
    async def add_ticker(self, ticker: str) -> None:
        """
        Add ticker to the active set. Takes effect on the next update cycle.
        Should also seed the cache immediately so the watchlist API returns a price
        without waiting for the next poll/tick.
        """
        ...

    @abstractmethod
    async def remove_ticker(self, ticker: str) -> None:
        """Remove ticker from active set and evict from cache."""
        ...

    @abstractmethod
    def get_tickers(self) -> list[str]:
        """Return currently tracked tickers."""
        ...
```

---

## `seed_prices.py`

Starting prices and GBM parameters for the 10 default tickers. Unknown tickers get `DEFAULT_PARAMS` and a random starting price.

```python
# backend/app/market/seed_prices.py
from __future__ import annotations
import random

# GBM parameters per ticker: (sigma, mu)
# sigma = annualized volatility, mu = annualized drift
TICKER_PARAMS: dict[str, tuple[float, float]] = {
    "AAPL":  (0.22, 0.05),
    "GOOGL": (0.25, 0.05),
    "MSFT":  (0.20, 0.05),
    "AMZN":  (0.28, 0.05),
    "TSLA":  (0.50, 0.03),  # high vol, low drift, mostly independent
    "NVDA":  (0.40, 0.08),  # high vol, strong drift (AI hype)
    "META":  (0.30, 0.05),
    "JPM":   (0.18, 0.04),  # low vol (bank)
    "V":     (0.17, 0.04),  # low vol (payments)
    "NFLX":  (0.35, 0.05),
}

DEFAULT_PARAMS: tuple[float, float] = (0.25, 0.05)

# Realistic starting prices (approximate to real values as of early 2026)
SEED_PRICES: dict[str, float] = {
    "AAPL":  191.00,
    "GOOGL": 175.00,
    "MSFT":  415.00,
    "AMZN":  198.00,
    "TSLA":  245.00,
    "NVDA":  875.00,
    "META":  515.00,
    "JPM":   215.00,
    "V":     275.00,
    "NFLX":  625.00,
}

# Correlation groups for Cholesky decomposition
# Tech stocks move together, finance stocks move together, TSLA is independent
SECTOR_TECH    = {"AAPL", "GOOGL", "MSFT", "AMZN", "META", "NVDA", "NFLX"}
SECTOR_FINANCE = {"JPM", "V"}
SECTOR_TSLA    = {"TSLA"}

# Pairwise correlation constants
CORR_TECH    = 0.6   # within tech sector
CORR_FINANCE = 0.5   # within finance sector
CORR_DEFAULT = 0.3   # cross-sector or unknown tickers


def get_params(ticker: str) -> tuple[float, float]:
    """Return (sigma, mu) for a ticker, defaulting if unknown."""
    return TICKER_PARAMS.get(ticker, DEFAULT_PARAMS)


def get_seed_price(ticker: str) -> float:
    """
    Return seed price for known tickers. Unknown tickers get a random price
    in [50, 300] — not seeded, so it varies per session.
    """
    return SEED_PRICES.get(ticker, random.uniform(50.0, 300.0))


def build_correlation_matrix(tickers: list[str]) -> list[list[float]]:
    """
    Build an n×n correlation matrix for the given ticker list.
    Diagonal = 1.0. Off-diagonal = sector-based correlation.
    """
    n = len(tickers)
    matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j:
                matrix[i][j] = 1.0
            else:
                ti, tj = tickers[i], tickers[j]
                if ti in SECTOR_TECH and tj in SECTOR_TECH:
                    matrix[i][j] = CORR_TECH
                elif ti in SECTOR_FINANCE and tj in SECTOR_FINANCE:
                    matrix[i][j] = CORR_FINANCE
                else:
                    matrix[i][j] = CORR_DEFAULT
    return matrix
```

---

## `simulator.py`

Two classes: `GBMSimulator` (pure math, no I/O) and `SimulatorDataSource` (asyncio wrapper).

### GBMSimulator

```python
# backend/app/market/simulator.py  (part 1: GBMSimulator)
from __future__ import annotations
import math
import random
import numpy as np
from app.market.seed_prices import (
    get_params,
    get_seed_price,
    build_correlation_matrix,
)

# dt for 500ms tick: fraction of a trading year
# Trading year = 252 days × 6.5 hours × 3600 seconds
_DEFAULT_DT = 0.5 / (252 * 6.5 * 3600)  # ≈ 8.48e-8


class GBMSimulator:
    """
    Pure-math GBM price simulator. No asyncio, no I/O — fully unit-testable.

    Prices follow:
        S(t+dt) = S(t) * exp((mu - 0.5*sigma²)*dt + sigma*sqrt(dt)*Z)

    Correlated moves across tickers via Cholesky decomposition of a
    sector-based correlation matrix.
    """

    def __init__(
        self,
        tickers: list[str],
        dt: float = _DEFAULT_DT,
        event_probability: float = 0.001,
    ) -> None:
        self._dt = dt
        self._event_probability = event_probability
        self._tickers: list[str] = []
        self._prices: dict[str, float] = {}
        self._cholesky: np.ndarray | None = None

        for ticker in tickers:
            self._add_ticker_internal(ticker)
        self._rebuild_cholesky()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def step(self) -> dict[str, float]:
        """
        Advance all prices by one dt tick. Returns {ticker: new_price}.
        Hot path — called every 500ms.
        """
        n = len(self._tickers)
        if n == 0:
            return {}

        # 1. Independent standard normals
        z_ind = np.random.standard_normal(n)

        # 2. Correlated normals via Cholesky
        z_corr = self._cholesky @ z_ind if self._cholesky is not None else z_ind

        # 3. Advance each price
        results: dict[str, float] = {}
        for i, ticker in enumerate(self._tickers):
            sigma, mu = get_params(ticker)
            s = self._prices[ticker]
            drift = (mu - 0.5 * sigma ** 2) * self._dt
            diffusion = sigma * math.sqrt(self._dt) * z_corr[i]
            s_new = s * math.exp(drift + diffusion)

            # 4. Random news event
            if random.random() < self._event_probability:
                shock = random.uniform(0.02, 0.05) * random.choice([-1, 1])
                s_new *= 1 + shock

            self._prices[ticker] = round(s_new, 2)
            results[ticker] = self._prices[ticker]

        return results

    def add_ticker(self, ticker: str) -> None:
        """Add ticker and rebuild Cholesky. O(n²) — fine for n < 50."""
        if ticker not in self._prices:
            self._add_ticker_internal(ticker)
            self._rebuild_cholesky()

    def remove_ticker(self, ticker: str) -> None:
        """Remove ticker and rebuild Cholesky."""
        if ticker in self._prices:
            self._tickers.remove(ticker)
            del self._prices[ticker]
            self._rebuild_cholesky()

    def get_price(self, ticker: str) -> float | None:
        return self._prices.get(ticker)

    def get_tickers(self) -> list[str]:
        return list(self._tickers)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _add_ticker_internal(self, ticker: str) -> None:
        self._tickers.append(ticker)
        self._prices[ticker] = get_seed_price(ticker)

    def _rebuild_cholesky(self) -> None:
        n = len(self._tickers)
        if n == 0:
            self._cholesky = None
            return
        corr = np.array(build_correlation_matrix(self._tickers))
        try:
            self._cholesky = np.linalg.cholesky(corr)
        except np.linalg.LinAlgError:
            # Fallback: identity (no correlation). Should not happen with valid params.
            self._cholesky = np.eye(n)
```

### SimulatorDataSource

```python
# backend/app/market/simulator.py  (part 2: SimulatorDataSource)
import asyncio
import logging
from app.market.interface import MarketDataSource
from app.market.cache import PriceCache

logger = logging.getLogger(__name__)


class SimulatorDataSource(MarketDataSource):
    """
    Asyncio wrapper around GBMSimulator. Implements MarketDataSource.
    Calls sim.step() every update_interval seconds and writes to PriceCache.
    """

    def __init__(
        self,
        price_cache: PriceCache,
        update_interval: float = 0.5,
        event_probability: float = 0.001,
    ) -> None:
        self._cache = price_cache
        self._update_interval = update_interval
        self._event_probability = event_probability
        self._sim: GBMSimulator | None = None
        self._task: asyncio.Task | None = None

    async def start(self, tickers: list[str]) -> None:
        self._sim = GBMSimulator(
            tickers=tickers,
            event_probability=self._event_probability,
        )
        # Seed cache immediately so first SSE push has data
        for ticker, price in self._sim.step().items():
            self._cache.update(ticker=ticker, price=price)

        self._task = asyncio.create_task(self._run_loop())
        logger.info("SimulatorDataSource started with tickers: %s", tickers)

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("SimulatorDataSource stopped")

    async def add_ticker(self, ticker: str) -> None:
        if self._sim is None:
            return
        self._sim.add_ticker(ticker)
        # Seed cache immediately
        price = self._sim.get_price(ticker)
        if price is not None:
            self._cache.update(ticker=ticker, price=price)

    async def remove_ticker(self, ticker: str) -> None:
        if self._sim is None:
            return
        self._sim.remove_ticker(ticker)
        self._cache.remove(ticker)

    def get_tickers(self) -> list[str]:
        return self._sim.get_tickers() if self._sim else []

    async def _run_loop(self) -> None:
        while True:
            try:
                prices = self._sim.step()
                for ticker, price in prices.items():
                    self._cache.update(ticker=ticker, price=price)
            except Exception:
                logger.exception("SimulatorDataSource: error in step()")
            await asyncio.sleep(self._update_interval)
```

---

## `massive_client.py`

Polls the Massive REST API for real market data.

```python
# backend/app/market/massive_client.py
from __future__ import annotations
import asyncio
import logging
from app.market.interface import MarketDataSource
from app.market.cache import PriceCache

logger = logging.getLogger(__name__)


class MassiveDataSource(MarketDataSource):
    """
    Polls Massive (Polygon.io) snapshot endpoint for all watched tickers
    in a single request. Defaults to 15s interval (free tier: 5 req/min).

    The synchronous RESTClient call runs in a thread pool via asyncio.to_thread
    to avoid blocking the event loop.
    """

    def __init__(
        self,
        api_key: str,
        price_cache: PriceCache,
        poll_interval: float = 15.0,
    ) -> None:
        self._api_key = api_key
        self._cache = price_cache
        self._poll_interval = poll_interval
        self._tickers: list[str] = []
        self._client = None
        self._task: asyncio.Task | None = None

    async def start(self, tickers: list[str]) -> None:
        from massive import RESTClient

        self._tickers = list(tickers)
        self._client = RESTClient(api_key=self._api_key)

        # Immediate first poll so cache is populated before SSE starts
        await self._poll_once()
        self._task = asyncio.create_task(self._run_loop())
        logger.info("MassiveDataSource started with tickers: %s", tickers)

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("MassiveDataSource stopped")

    async def add_ticker(self, ticker: str) -> None:
        if ticker not in self._tickers:
            self._tickers.append(ticker)
            # Fetch the new ticker immediately so watchlist shows a price
            await self._poll_once(tickers=[ticker])

    async def remove_ticker(self, ticker: str) -> None:
        if ticker in self._tickers:
            self._tickers.remove(ticker)
        self._cache.remove(ticker)

    def get_tickers(self) -> list[str]:
        return list(self._tickers)

    async def _run_loop(self) -> None:
        while True:
            await asyncio.sleep(self._poll_interval)
            await self._poll_once()

    async def _poll_once(self, tickers: list[str] | None = None) -> None:
        """
        Fetch snapshots for the given tickers (or all watched tickers).
        Runs the synchronous SDK call in a thread to avoid blocking the event loop.
        """
        target = tickers if tickers is not None else self._tickers
        if not target:
            return

        try:
            from massive.rest.models import SnapshotMarketType

            snapshots = await asyncio.to_thread(
                lambda: list(
                    self._client.get_snapshot_all(
                        market_type=SnapshotMarketType.STOCKS,
                        tickers=target,
                    )
                )
            )
            for snap in snapshots:
                try:
                    price = snap.last_trade.price
                    # Massive timestamps are Unix milliseconds — convert to seconds
                    timestamp = snap.last_trade.timestamp / 1000.0
                    self._cache.update(
                        ticker=snap.ticker,
                        price=price,
                        timestamp=timestamp,
                    )
                except AttributeError:
                    # Ticker has no recent trade data (e.g., illiquid, halted)
                    logger.warning("MassiveDataSource: no trade data for %s", snap.ticker)

        except Exception as exc:
            # 401, 429, network errors — log and retry on next interval
            logger.error("MassiveDataSource: poll failed: %s", exc)
```

**Error handling summary:**

| Error | Cause | Behavior |
|-------|-------|----------|
| `401 Unauthorized` | Bad/expired API key | Logged as error; cache unchanged |
| `429 Too Many Requests` | Rate limit hit | Logged as error; retry next interval |
| `AttributeError` on snap fields | No recent trade data | Logged as warning; ticker skipped |
| Network error | Connection issue | Logged as error; retry next interval |

---

## `factory.py`

Reads `MASSIVE_API_KEY` from the environment and returns the appropriate `MarketDataSource` instance. This is the only place in the codebase where the concrete implementation is referenced.

```python
# backend/app/market/factory.py
from __future__ import annotations
import os
from app.market.cache import PriceCache
from app.market.interface import MarketDataSource


def create_market_data_source(cache: PriceCache) -> MarketDataSource:
    """
    Factory: reads MASSIVE_API_KEY from environment.

    MASSIVE_API_KEY set and non-empty → MassiveDataSource (real data, 15s poll)
    MASSIVE_API_KEY absent or empty   → SimulatorDataSource (GBM, 500ms ticks)
    """
    api_key = os.environ.get("MASSIVE_API_KEY", "").strip()

    if api_key:
        from app.market.massive_client import MassiveDataSource
        return MassiveDataSource(api_key=api_key, price_cache=cache)
    else:
        from app.market.simulator import SimulatorDataSource
        return SimulatorDataSource(price_cache=cache)
```

**Application startup** (`backend/app/main.py`) — lifecycle integration:

```python
# backend/app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.market.cache import PriceCache
from app.market.factory import create_market_data_source
from app.database import get_watchlist_tickers  # reads watchlist table

price_cache = PriceCache()
market_source = create_market_data_source(price_cache)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize DB, load watchlist, start market data
    from app.database import init_db
    await init_db()
    tickers = await get_watchlist_tickers()
    await market_source.start(tickers)
    yield
    # Shutdown: stop market data task
    await market_source.stop()


app = FastAPI(lifespan=lifespan)

# Make cache and source available to route handlers
app.state.price_cache = price_cache
app.state.market_source = market_source
```

---

## `stream.py`

SSE endpoint. Reads from `PriceCache` every 500ms and pushes all prices to connected clients.

```python
# backend/app/market/stream.py
from __future__ import annotations
import asyncio
import json
import logging
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from app.market.cache import PriceCache

logger = logging.getLogger(__name__)
router = APIRouter()

_SSE_INTERVAL = 0.5  # seconds between pushes


@router.get("/api/stream/prices")
async def stream_prices(request: Request) -> StreamingResponse:
    cache: PriceCache = request.app.state.price_cache
    return StreamingResponse(
        _price_generator(request, cache),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disables nginx buffering
        },
    )


async def _price_generator(request: Request, cache: PriceCache):
    """
    Async generator. Yields SSE events every 500ms.

    Uses cache.version to detect whether anything changed since the last push.
    If nothing changed, sends a comment (: keepalive) to keep the connection open
    rather than re-sending identical data.
    """
    # Tell the client to reconnect after 1 second if the connection drops
    yield "retry: 1000\n\n"

    last_version = -1

    while True:
        # Check for client disconnect
        if await request.is_disconnected():
            logger.debug("SSE client disconnected")
            break

        current_version = cache.version
        if current_version != last_version:
            all_prices = cache.get_all()
            payload = {
                ticker: update.to_dict()
                for ticker, update in all_prices.items()
            }
            yield f"data: {json.dumps(payload)}\n\n"
            last_version = current_version
        else:
            # No new data — send keepalive comment to prevent proxy timeouts
            yield ": keepalive\n\n"

        await asyncio.sleep(_SSE_INTERVAL)
```

**Client-side connection** (TypeScript, in the frontend):

```typescript
// frontend/src/hooks/usePriceStream.ts
const es = new EventSource("/api/stream/prices");

es.onmessage = (event) => {
  const prices: Record<string, PriceUpdate> = JSON.parse(event.data);
  // prices["AAPL"] → { ticker, price, previous_price, change, change_percent, direction, timestamp }
  dispatch(updatePrices(prices));
};

es.onerror = () => {
  // EventSource auto-reconnects using the retry: 1000 directive
  setConnectionStatus("reconnecting");
};
```

---

## Watchlist API Integration

When the user adds or removes a ticker via the watchlist API, the route handler must also update the market data source so the SSE stream starts/stops providing prices for that ticker.

```python
# backend/app/api/watchlist.py
from fastapi import APIRouter, Request, HTTPException
from app.database import add_watchlist_ticker, remove_watchlist_ticker

router = APIRouter()


@router.post("/api/watchlist")
async def add_ticker(body: dict, request: Request):
    ticker = body.get("ticker", "").upper().strip()
    if not ticker:
        raise HTTPException(400, "ticker required")

    source = request.app.state.market_source
    cache  = request.app.state.price_cache

    # 1. Persist to DB
    await add_watchlist_ticker(ticker)

    # 2. Start tracking prices (seeds cache immediately)
    await source.add_ticker(ticker)

    # 3. Return the new ticker with its current price
    price_update = cache.get(ticker)
    return {
        "ticker": ticker,
        "price": price_update.price if price_update else None,
    }


@router.delete("/api/watchlist/{ticker}")
async def remove_ticker(ticker: str, request: Request):
    ticker = ticker.upper()
    source = request.app.state.market_source

    await remove_watchlist_ticker(ticker)
    await source.remove_ticker(ticker)  # also evicts from cache

    return {"ticker": ticker, "removed": True}
```

---

## Unit Testing

`GBMSimulator` has no I/O — test it synchronously.

```python
# backend/tests/market/test_gbm_simulator.py
import pytest
from app.market.simulator import GBMSimulator


def test_step_returns_all_tickers():
    sim = GBMSimulator(["AAPL", "TSLA"])
    prices = sim.step()
    assert set(prices.keys()) == {"AAPL", "TSLA"}


def test_prices_are_positive():
    sim = GBMSimulator(["AAPL", "GOOGL", "MSFT"])
    for _ in range(100):
        prices = sim.step()
        for ticker, price in prices.items():
            assert price > 0, f"{ticker} went non-positive"


def test_add_ticker_appears_in_next_step():
    sim = GBMSimulator(["AAPL"])
    sim.add_ticker("NVDA")
    prices = sim.step()
    assert "NVDA" in prices


def test_remove_ticker_absent_from_next_step():
    sim = GBMSimulator(["AAPL", "GOOGL"])
    sim.remove_ticker("GOOGL")
    prices = sim.step()
    assert "GOOGL" not in prices


def test_prices_rounded_to_two_decimal_places():
    sim = GBMSimulator(["MSFT"])
    for _ in range(20):
        prices = sim.step()
        for price in prices.values():
            assert price == round(price, 2)


def test_unknown_ticker_gets_reasonable_price():
    sim = GBMSimulator(["FAKE"])
    prices = sim.step()
    assert 1.0 < prices["FAKE"] < 10_000.0
```

```python
# backend/tests/market/test_price_cache.py
from app.market.cache import PriceCache


def test_update_and_get():
    cache = PriceCache()
    cache.update("AAPL", 191.50)
    entry = cache.get("AAPL")
    assert entry.price == 191.50
    assert entry.ticker == "AAPL"


def test_previous_price_is_previous_update():
    cache = PriceCache()
    cache.update("AAPL", 190.00)
    cache.update("AAPL", 192.00)
    entry = cache.get("AAPL")
    assert entry.previous_price == 190.00
    assert entry.price == 192.00


def test_first_update_previous_equals_price():
    cache = PriceCache()
    cache.update("TSLA", 245.00)
    entry = cache.get("TSLA")
    assert entry.previous_price == entry.price


def test_direction():
    cache = PriceCache()
    cache.update("AAPL", 190.00)
    cache.update("AAPL", 192.00)
    assert cache.get("AAPL").direction == "up"

    cache.update("AAPL", 189.00)
    assert cache.get("AAPL").direction == "down"


def test_version_increments_on_update():
    cache = PriceCache()
    v0 = cache.version
    cache.update("AAPL", 191.00)
    assert cache.version == v0 + 1


def test_remove_evicts_ticker():
    cache = PriceCache()
    cache.update("AAPL", 191.00)
    cache.remove("AAPL")
    assert cache.get("AAPL") is None


def test_get_all_returns_shallow_copy():
    cache = PriceCache()
    cache.update("AAPL", 191.00)
    snapshot = cache.get_all()
    cache.update("AAPL", 195.00)
    # The snapshot is a copy — the original dict should not be mutated
    assert snapshot["AAPL"].price == 191.00
```

```python
# backend/tests/market/test_simulator_source.py
import asyncio
import pytest
from app.market.simulator import SimulatorDataSource
from app.market.cache import PriceCache


@pytest.mark.asyncio
async def test_start_seeds_cache():
    cache = PriceCache()
    source = SimulatorDataSource(price_cache=cache, update_interval=10.0)
    await source.start(["AAPL", "GOOGL"])

    assert cache.get("AAPL") is not None
    assert cache.get("GOOGL") is not None

    await source.stop()


@pytest.mark.asyncio
async def test_add_ticker_seeds_cache():
    cache = PriceCache()
    source = SimulatorDataSource(price_cache=cache, update_interval=10.0)
    await source.start(["AAPL"])
    await source.add_ticker("TSLA")

    assert cache.get("TSLA") is not None
    await source.stop()


@pytest.mark.asyncio
async def test_remove_ticker_evicts_cache():
    cache = PriceCache()
    source = SimulatorDataSource(price_cache=cache, update_interval=10.0)
    await source.start(["AAPL", "TSLA"])
    await source.remove_ticker("TSLA")

    assert cache.get("TSLA") is None
    await source.stop()


@pytest.mark.asyncio
async def test_prices_update_over_time():
    cache = PriceCache()
    source = SimulatorDataSource(price_cache=cache, update_interval=0.05)
    await source.start(["AAPL"])

    price_before = cache.get("AAPL").price
    await asyncio.sleep(0.2)  # wait for a few ticks
    price_after = cache.get("AAPL").price

    await source.stop()
    # Price should have moved (extremely unlikely to be identical after 4 ticks)
    assert price_before != price_after
```

---

## Data Flow Summary

```
┌──────────────────────────────────────────────────────────────┐
│  Startup                                                     │
│  ──────                                                      │
│  init_db()  →  get_watchlist_tickers()  →  source.start()   │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│  Background loop (every 500ms or 15s)                        │
│  ──────────────────────────────────                          │
│  SimulatorDataSource._run_loop()                             │
│    └─ sim.step()  →  cache.update(ticker, price)  ×N        │
│                                                              │
│  MassiveDataSource._run_loop()                               │
│    └─ _poll_once()  →  cache.update(ticker, price)  ×N      │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│  PriceCache (shared in-memory state)                         │
│  ──────────────────────────────────                          │
│  { "AAPL": PriceUpdate, "TSLA": PriceUpdate, ... }          │
│  version: int (increments on every write)                    │
└──────────────────────────────────────────────────────────────┘
                    │                │
          ┌─────────┘                └──────────────────┐
          ▼                                             ▼
┌─────────────────────┐              ┌──────────────────────────┐
│  SSE stream         │              │  Trade execution          │
│  ─────────────────  │              │  Portfolio valuation      │
│  GET /api/stream/   │              │  Watchlist API response   │
│  prices             │              └──────────────────────────┘
│                     │
│  Every 500ms:       │
│  push get_all()     │
│  to all clients     │
└─────────────────────┘
```

---

## `__init__.py`

Exports the public API of the market module so routes only need to import from `app.market`.

```python
# backend/app/market/__init__.py
from app.market.cache import PriceCache
from app.market.factory import create_market_data_source
from app.market.interface import MarketDataSource
from app.market.models import PriceUpdate
from app.market.stream import router as stream_router

__all__ = [
    "PriceCache",
    "create_market_data_source",
    "MarketDataSource",
    "PriceUpdate",
    "stream_router",
]
```
