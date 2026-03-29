# Market Data Interface

## Overview

The market data layer provides a unified interface for price data, backed by either the **Massive (Polygon.io) REST API** (real market data) or the **GBM Simulator** (default). The active source is selected at startup based on the `MASSIVE_API_KEY` environment variable — all downstream code is agnostic to which is running.

## Selection Logic

```
MASSIVE_API_KEY set and non-empty  →  MassiveDataSource   (real data, 15s poll)
MASSIVE_API_KEY absent or empty    →  SimulatorDataSource (GBM, 500ms ticks)
```

Factory: `backend/app/market/factory.py`

```python
from app.market.factory import create_market_data_source
from app.market.cache import PriceCache

cache = PriceCache()
source = create_market_data_source(cache)   # reads MASSIVE_API_KEY from env

await source.start(["AAPL", "GOOGL", "MSFT"])
# ... app runs ...
await source.stop()
```

## Abstract Interface

`backend/app/market/interface.py` — `MarketDataSource`

```python
class MarketDataSource(ABC):
    async def start(self, tickers: list[str]) -> None: ...
    async def stop(self) -> None: ...
    async def add_ticker(self, ticker: str) -> None: ...
    async def remove_ticker(self, ticker: str) -> None: ...
    def get_tickers(self) -> list[str]: ...
```

| Method | Description |
|--------|-------------|
| `start(tickers)` | Begin producing price updates; spawns background task |
| `stop()` | Cancel background task; safe to call multiple times |
| `add_ticker(ticker)` | Add a ticker to the active set; takes effect on next update cycle |
| `remove_ticker(ticker)` | Remove ticker from active set and evict from cache |
| `get_tickers()` | Return currently tracked tickers |

## Price Cache

`backend/app/market/cache.py` — `PriceCache`

The cache is the shared state that decouples the market data source from consumers. The source writes; SSE streaming, portfolio valuation, and trade execution read.

```python
cache.update(ticker="AAPL", price=191.50)   # called by source on every tick
cache.get("AAPL")          # → PriceUpdate | None
cache.get_all()            # → dict[str, PriceUpdate]  (shallow copy)
cache.get_price("AAPL")    # → float | None
cache.remove("AAPL")       # evict (called on remove_ticker)
cache.version              # int, increments on every update (for SSE change detection)
```

## Price Update Model

`backend/app/market/models.py` — `PriceUpdate` (frozen dataclass)

| Field | Type | Description |
|-------|------|-------------|
| `ticker` | `str` | Symbol, e.g. `"AAPL"` |
| `price` | `float` | Current price, rounded to 2dp |
| `previous_price` | `float` | Previous price (first update: same as price) |
| `timestamp` | `float` | Unix seconds |
| `change` | property | `price - previous_price` |
| `change_percent` | property | `(price - prev) / prev * 100` |
| `direction` | property | `"up"` / `"down"` / `"flat"` |

`PriceUpdate.to_dict()` produces the JSON sent over SSE:

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

## SSE Stream

`backend/app/market/stream.py` — `GET /api/stream/prices`

The SSE endpoint reads from `PriceCache` every 500ms and pushes all prices to connected clients. It uses `cache.version` to skip unchanged states.

```
data: {"AAPL": {...}, "GOOGL": {...}, ...}
```

- Client uses native `EventSource` API.
- Auto-reconnects via `retry: 1000` directive.
- Adding/removing a ticker takes effect on the next push cycle — no client reconnect needed.

## File Map

```
backend/app/market/
├── interface.py       # MarketDataSource ABC
├── cache.py           # PriceCache (thread-safe shared state)
├── models.py          # PriceUpdate dataclass
├── factory.py         # create_market_data_source() — env-driven selection
├── simulator.py       # SimulatorDataSource + GBMSimulator
├── massive_client.py  # MassiveDataSource
├── seed_prices.py     # Starting prices and GBM params for default tickers
└── stream.py          # SSE router (reads from PriceCache)
```
