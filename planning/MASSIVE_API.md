# Massive API Integration

## Overview

Massive (formerly Polygon.io, rebranded October 2025) provides REST APIs for US equities market data. FinAlly uses the snapshot endpoint to batch-fetch current prices for all watched tickers in a single request.

**Python package**: `massive` (replaces `polygon-api-client`)

```bash
uv add massive
```

## Authentication

Set `MASSIVE_API_KEY` in `.env`. The factory reads this at startup.

```python
from massive import RESTClient

client = RESTClient(api_key="your-key-here")
# or, with MASSIVE_API_KEY env var set:
client = RESTClient()
```

## Key Endpoint: Full Market Snapshot

**GET** `/v2/snapshot/locale/us/markets/stocks/tickers`

Returns the latest trade, quote, and daily aggregate for a list of tickers — all in one request. This is the only endpoint FinAlly uses.

### SDK call

```python
from massive import RESTClient
from massive.rest.models import SnapshotMarketType

client = RESTClient(api_key="...")

# Fetch snapshots for specific tickers
snapshots = client.get_snapshot_all(
    market_type=SnapshotMarketType.STOCKS,
    tickers=["AAPL", "TSLA", "NVDA"],
)

for snap in snapshots:
    print(snap.ticker, snap.last_trade.price, snap.last_trade.timestamp)
```

### Response object fields

Each item in the iterable is a ticker snapshot:

| Field | Type | Description |
|-------|------|-------------|
| `snap.ticker` | `str` | Symbol, e.g. `"AAPL"` |
| `snap.last_trade.price` | `float` | Most recent trade price |
| `snap.last_trade.timestamp` | `int` | Trade time, Unix **milliseconds** |
| `snap.last_trade.size` | `int` | Trade size (shares) |
| `snap.last_quote.bid` | `float` | Best bid |
| `snap.last_quote.ask` | `float` | Best ask |
| `snap.day.open` | `float` | Today's open |
| `snap.day.high` | `float` | Today's high |
| `snap.day.low` | `float` | Today's low |
| `snap.day.close` | `float` | Today's close (current or end-of-day) |
| `snap.day.volume` | `float` | Today's volume |
| `snap.prev_day.close` | `float` | Previous day's close |
| `snap.todays_change` | `float` | Price change from previous close |
| `snap.todays_change_perc` | `float` | Percentage change from previous close |
| `snap.updated` | `int` | Unix timestamp of last update |

### Timestamp conversion

Massive timestamps in `last_trade.timestamp` are Unix **milliseconds**. Convert to seconds before writing to `PriceCache`:

```python
timestamp_seconds = snap.last_trade.timestamp / 1000.0
```

## Rate Limits

| Tier | Limit | Recommended poll interval |
|------|-------|--------------------------|
| Free | 5 req/min | 15 seconds (default) |
| Paid | Unlimited (stay under 100 req/s) | 2–5 seconds |

FinAlly defaults to `poll_interval=15.0`. Override by passing a different value to `MassiveDataSource`.

## How FinAlly Uses It

`MassiveDataSource` (`backend/app/market/massive_client.py`):

1. `start(tickers)` — creates `RESTClient`, runs an immediate first poll, then starts a background asyncio loop.
2. Loop: `asyncio.sleep(interval)` → `_poll_once()` → writes results to `PriceCache`.
3. The synchronous `RESTClient` call runs in a thread via `asyncio.to_thread()` to avoid blocking the event loop.
4. Errors (401, 429, network failures) are logged and retried on the next interval — the cache retains the last known price.

```python
# Polling pattern used in massive_client.py
snapshots = await asyncio.to_thread(
    lambda: client.get_snapshot_all(
        market_type=SnapshotMarketType.STOCKS,
        tickers=self._tickers,
    )
)
for snap in snapshots:
    cache.update(
        ticker=snap.ticker,
        price=snap.last_trade.price,
        timestamp=snap.last_trade.timestamp / 1000.0,
    )
```

## Real-Time vs End-of-Day

| Use case | Field | Notes |
|----------|-------|-------|
| Live price during market hours | `last_trade.price` | Updates as trades execute |
| Daily closing price | `day.close` | Populated after market close |
| Change from yesterday | `todays_change_perc` | Based on previous close |

FinAlly uses `last_trade.price` exclusively. This reflects the most recent transaction — during market hours it is effectively real-time; after hours it is the last trade of the session.

Snapshot data resets at 3:30 AM EST and begins populating ~4:00 AM EST as exchanges report.

## Ticker Support

Any valid US equity ticker is supported. Tickers not recognized by the API return no snapshot entry (they are silently skipped in `_poll_once`). Unlike the simulator, unsupported or invalid tickers produce no price data.

## Error Handling

Common failure modes handled in `_poll_once`:

| Error | Cause | Behavior |
|-------|-------|----------|
| `401 Unauthorized` | Bad or expired API key | Logged as error; cache unchanged |
| `429 Too Many Requests` | Rate limit exceeded | Logged as error; retry on next interval |
| `AttributeError` on snap fields | Ticker has no recent trade data | Logged as warning; that ticker skipped |
| Network error | Connection issue | Logged as error; retry on next interval |

## Dependencies

```toml
# backend/pyproject.toml
[project]
dependencies = [
    "massive",
    ...
]
```
