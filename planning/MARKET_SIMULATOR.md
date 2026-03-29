# Market Simulator

## Overview

The simulator produces realistic-looking stock price movements without any external API. It runs as an in-process background task and is the default when `MASSIVE_API_KEY` is not set.

Two classes collaborate: `GBMSimulator` (pure math, no I/O) and `SimulatorDataSource` (asyncio wrapper that feeds the `PriceCache`).

Files: `backend/app/market/simulator.py`, `backend/app/market/seed_prices.py`

## GBM Simulator

### Math

Prices follow **Geometric Brownian Motion**:

```
S(t+dt) = S(t) * exp( (mu - 0.5*sigma^2)*dt  +  sigma * sqrt(dt) * Z )
```

| Symbol | Meaning |
|--------|---------|
| `S(t)` | Current price |
| `mu` | Annualized drift (expected return) |
| `sigma` | Annualized volatility |
| `dt` | Time step as fraction of a trading year |
| `Z` | Correlated standard normal random variable |

At 500ms ticks:
```
dt = 0.5 / (252 * 6.5 * 3600)  ≈  8.48e-8
```

This tiny `dt` produces sub-cent moves per tick that accumulate naturally — prices drift and oscillate believably over time without mean reversion or clamping.

### Correlated Moves

Tickers move together in sector groups. The simulator builds a correlation matrix, Cholesky-decomposes it, and multiplies independent normal draws to produce correlated ones.

```python
z_independent = np.random.standard_normal(n)   # one draw per ticker
z_correlated  = cholesky @ z_independent        # apply correlations
```

Correlation structure (`seed_prices.py`):

| Relationship | Correlation |
|---|---|
| Tech stocks (AAPL, GOOGL, MSFT, AMZN, META, NVDA, NFLX) | 0.6 |
| Finance stocks (JPM, V) | 0.5 |
| TSLA with anything | 0.3 |
| Cross-sector / unknown | 0.3 |

Cholesky is rebuilt whenever a ticker is added or removed. For `n < 50` this is fast enough to happen synchronously.

### Random Events

Each tick, each ticker has a 0.1% chance of a "news event": an instantaneous 2–5% shock in a random direction. With 10 tickers at 2 ticks/second, an event fires roughly every 50 seconds, adding drama without being disruptive.

```python
if random.random() < 0.001:
    shock = random.uniform(0.02, 0.05) * random.choice([-1, 1])
    self._prices[ticker] *= 1 + shock
```

### Per-Ticker Parameters (`seed_prices.py`)

| Ticker | sigma | mu | Notes |
|--------|-------|-----|-------|
| AAPL | 0.22 | 0.05 | |
| GOOGL | 0.25 | 0.05 | |
| MSFT | 0.20 | 0.05 | |
| AMZN | 0.28 | 0.05 | |
| TSLA | 0.50 | 0.03 | High vol, independent |
| NVDA | 0.40 | 0.08 | High vol, strong drift |
| META | 0.30 | 0.05 | |
| JPM | 0.18 | 0.04 | Low vol (bank) |
| V | 0.17 | 0.04 | Low vol (payments) |
| NFLX | 0.35 | 0.05 | |
| (unknown) | 0.25 | 0.05 | Default params |

Seed prices (starting values) are also defined for the 10 default tickers. Unknown tickers get a deterministic starting price via `random.uniform(50.0, 300.0)` — the randomness is not seeded, so the price varies per session, but is always in a reasonable range.

## GBMSimulator API

```python
sim = GBMSimulator(tickers=["AAPL", "GOOGL"])

prices = sim.step()           # → {"AAPL": 190.12, "GOOGL": 175.44}
sim.add_ticker("TSLA")        # rebuilds Cholesky
sim.remove_ticker("GOOGL")    # rebuilds Cholesky
sim.get_price("AAPL")         # → float | None
sim.get_tickers()             # → ["AAPL", "TSLA"]
```

`step()` is the hot path — called every 500ms. It:
1. Generates `n` independent normal draws
2. Applies Cholesky to correlate them
3. Advances each price with the GBM formula
4. Optionally fires a random event
5. Returns all prices rounded to 2dp

## SimulatorDataSource

Wraps `GBMSimulator` in the `MarketDataSource` interface. Runs an asyncio task that calls `sim.step()` every 500ms and writes results to `PriceCache`.

```python
source = SimulatorDataSource(price_cache=cache)
await source.start(["AAPL", "TSLA"])   # seeds cache immediately, starts loop
await source.add_ticker("NVDA")         # sim.add_ticker + seed cache
await source.remove_ticker("TSLA")     # sim.remove_ticker + cache.remove
await source.stop()                    # cancels asyncio task
```

On `start()`, the cache is seeded immediately with the initial GBM prices so the SSE stream has data to send before the first tick fires.

### Background Loop

```python
async def _run_loop(self):
    while True:
        prices = self._sim.step()
        for ticker, price in prices.items():
            self._cache.update(ticker=ticker, price=price)
        await asyncio.sleep(0.5)
```

Exceptions in `step()` are caught and logged; the loop continues. This prevents a single bad tick from killing the stream.

## Configuration

`SimulatorDataSource` accepts:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `update_interval` | `0.5` | Seconds between ticks |
| `event_probability` | `0.001` | Per-tick per-ticker event chance |

`GBMSimulator` also accepts `dt` (defaults to the 500ms/trading-year ratio).

## Design Notes

- **GBMSimulator has no I/O** — it's pure math and can be unit-tested synchronously.
- **SimulatorDataSource owns the asyncio lifecycle** — it is the only thing that calls `step()`.
- **Cholesky rebuild is O(n²)** — acceptable for `n < 50`; would need optimization for larger watchlists.
- **No mean reversion** — prices can drift far from their starting values over long sessions. This is intentional: it creates visible P&L swings in the demo.
- **Arbitrary tickers are supported** — any string gets `DEFAULT_PARAMS` and a random seed price, so the AI assistant can add any ticker to the watchlist without breaking the simulation.
