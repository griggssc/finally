# Market Data Backend — Code Review

**Reviewed:** 2026-03-30
**Source commit:** `f89aa14` (post-review fixes applied)
**Reviewer:** Claude Sonnet 4.6

---

## Test Results

```
73 passed in 1.25s   (all tests pass)
Lint: ruff — All checks passed
```

### Coverage by file

| File | Stmts | Miss | Cover | Notes |
|---|---|---|---|---|
| `models.py` | 26 | 0 | **100%** | |
| `cache.py` | 39 | 0 | **100%** | |
| `interface.py` | 13 | 0 | **100%** | |
| `seed_prices.py` | 8 | 0 | **100%** | |
| `factory.py` | 15 | 0 | **100%** | |
| `simulator.py` | 139 | 3 | **98%** | 3 lines: debug log + stop path |
| `massive_client.py` | 68 | 5 | **93%** | `_fetch_snapshots` body never runs (mocked) |
| `stream.py` | 36 | 24 | **33%** | Entire SSE generator untested |
| **TOTAL** | **350** | **32** | **91%** | |

---

## Summary Verdict

The implementation is **well-structured and correct**. The design spec is faithfully followed: the abstract interface, two concrete implementations, factory selection, price cache, and SSE stream are all present and coherent. All 73 tests pass and the linter is clean.

The main concerns — ordered by severity — are below.

---

## Issues

### 1. `stream.py` has 33% coverage — SSE endpoint is untested

**Severity: High**

The `_generate_events` async generator (the core of the SSE stream) has no tests at all. This is the most user-visible part of the market data system — it is what the browser connects to — and it is also the component most likely to fail silently (no error, just a dead stream).

Missing test coverage includes:
- `retry: 1000` is the first event yielded
- Events are sent when the cache version changes
- Events are not sent (or a keepalive is sent) when version is unchanged
- Client disconnect terminates the generator cleanly
- Empty cache: no `data:` events are emitted

**Suggested tests:**

```python
@pytest.mark.asyncio
async def test_retry_directive_is_first_event():
    cache = PriceCache()
    request = AsyncMock()
    request.client = None
    request.is_disconnected = AsyncMock(side_effect=[False, False, True])

    events = []
    async for event in _generate_events(cache, request, interval=0.01):
        events.append(event)

    assert events[0] == "retry: 1000\n\n"


@pytest.mark.asyncio
async def test_price_event_emitted_on_cache_update():
    cache = PriceCache()
    cache.update("AAPL", 190.50)
    request = AsyncMock()
    request.client = None
    request.is_disconnected = AsyncMock(side_effect=[False, True])

    events = []
    async for event in _generate_events(cache, request, interval=0.01):
        events.append(event)

    data_events = [e for e in events if e.startswith("data:")]
    assert len(data_events) == 1
    payload = json.loads(data_events[0].removeprefix("data: ").strip())
    assert "AAPL" in payload
    assert payload["AAPL"]["price"] == 190.50
```

---

### 2. No keepalive when cache is unchanged

**Severity: Medium**

The design document specifies:

> If nothing changed, sends a comment (`: keepalive`) to keep the connection open

The implementation does not do this. When `current_version == last_version`, the loop just sleeps without sending anything:

```python
# stream.py — actual behavior
if current_version != last_version:
    ...
    yield f"data: {payload}\n\n"
    last_version = current_version
# else: nothing sent — silent sleep
```

With the simulator running at 500ms, this rarely matters in practice. But with `MassiveDataSource` polling at 15s intervals, the SSE stream goes silent for up to 15 seconds between events. Proxies with aggressive idle timeouts (nginx defaults to 60s, some cloud load balancers to 30s) may close the connection in that window.

**Fix:**

```python
if current_version != last_version:
    ...
    yield f"data: {payload}\n\n"
    last_version = current_version
else:
    yield ": keepalive\n\n"
```

---

### 3. `MassiveDataSource.add_ticker` does not immediately seed the cache

**Severity: Medium**

`SimulatorDataSource.add_ticker` seeds the cache immediately so the watchlist API returns a price right away. `MassiveDataSource.add_ticker` only appends to the ticker list — the cache won't have a price until the next poll fires (up to 15 seconds).

```python
# massive_client.py — current
async def add_ticker(self, ticker: str) -> None:
    ticker = ticker.upper().strip()
    if ticker not in self._tickers:
        self._tickers.append(ticker)
        logger.info("Massive: added ticker %s (will appear on next poll)", ticker)
        # No immediate fetch — new ticker has no price for up to 15s
```

The watchlist `POST /api/watchlist` endpoint returns `{"ticker": "X", "price": null}` for up to 15 seconds after adding a ticker via the Massive source. This is a visible inconsistency with the simulator path.

**Suggested fix:** trigger `_poll_once(tickers=[ticker])` immediately on add — it costs one extra API call but is within the free tier limits given how infrequently tickers are added.

```python
async def add_ticker(self, ticker: str) -> None:
    ticker = ticker.upper().strip()
    if ticker not in self._tickers:
        self._tickers.append(ticker)
        await self._poll_once(tickers=[ticker])  # seed cache immediately
```

Note: this requires `_poll_once` to accept an optional `tickers` override — a small refactor.

---

### 4. `cache.remove()` does not increment `version`

**Severity: Low**

When a ticker is removed from the watchlist, `cache.remove()` evicts it from `_prices` but does not bump `_version`. The SSE stream uses `version` to detect changes, so after a removal the stream will not push the updated (smaller) set until the next price update arrives from another ticker.

With the simulator at 500ms ticks, this means at most a 500ms delay before the removed ticker disappears from the SSE payload — acceptable in practice. But it's a logic gap: a removal is a state change that should trigger a push.

```python
# cache.py — current
def remove(self, ticker: str) -> None:
    with self._lock:
        self._prices.pop(ticker, None)
        # _version not incremented

# Fix:
def remove(self, ticker: str) -> None:
    with self._lock:
        self._prices.pop(ticker, None)
        self._version += 1
```

---

### 5. Tests reach into private attributes

**Severity: Low**

Two tests in `test_simulator.py` inspect internal state directly:

```python
def test_cholesky_rebuilds_on_add(self):
    assert sim._cholesky is None     # private attribute
    sim.add_ticker("GOOGL")
    assert sim._cholesky is not None  # private attribute

def test_add_duplicate_is_noop(self):
    assert len(sim._tickers) == 1    # private attribute
```

These tests break if the Cholesky approach is ever replaced (e.g., with a different correlation method) even if the external behavior is identical. The `_cholesky` test is particularly fragile — the internal representation is an implementation detail.

Better approach: test the observable behavior.

```python
def test_cholesky_active_with_multiple_tickers(self):
    """With 2+ tickers, correlated moves are produced (step doesn't crash)."""
    sim = GBMSimulator(tickers=["AAPL", "GOOGL"])
    prices = sim.step()
    assert len(prices) == 2  # both updated, correlation matrix worked

def test_add_duplicate_is_noop(self):
    sim = GBMSimulator(tickers=["AAPL"])
    sim.add_ticker("AAPL")
    assert sim.get_tickers() == ["AAPL"]  # use public API
```

---

### 6. TSLA is in the tech correlation group but treated as independent

**Severity: Low (readability)**

`seed_prices.py` includes TSLA in `CORRELATION_GROUPS["tech"]`:

```python
CORRELATION_GROUPS: dict[str, set[str]] = {
    "tech": {"AAPL", "GOOGL", "MSFT", "AMZN", "META", "NVDA", "NFLX"},
    "finance": {"JPM", "V"},
}
```

But `_pairwise_correlation` immediately overrides this with a special case:

```python
if t1 == "TSLA" or t2 == "TSLA":
    return TSLA_CORR  # always 0.3, regardless of sector
```

Wait — TSLA is actually *not* in `CORRELATION_GROUPS["tech"]` in this code. The check is order-correct: TSLA is handled before the tech group check. However, the `TSLA_CORR` constant in `seed_prices.py` exists alongside `INTRA_TECH_CORR`, `INTRA_FINANCE_CORR`, and `CROSS_GROUP_CORR`, and there is no comment explaining why TSLA is a special case rather than just using `CROSS_GROUP_CORR` (both are 0.3). The constants add a minor confusion since `TSLA_CORR == CROSS_GROUP_CORR == 0.3` — they are the same value. The intent (TSLA is volatile and independent) should either be documented in a comment or the `TSLA_CORR` constant should be given a distinct value to justify its existence.

---

### 7. `_fetch_snapshots` is not covered by tests

**Severity: Informational**

All `MassiveDataSource` tests mock `_fetch_snapshots` at the method level:

```python
with patch.object(source, "_fetch_snapshots", return_value=mock_snapshots):
    await source._poll_once()
```

This means the actual body of `_fetch_snapshots` — which does the lazy `from massive.rest.models import SnapshotMarketType` import and calls `self._client.get_snapshot_all(...)` — is never executed in the test suite. The uncovered lines 127-129 in the coverage report are exactly this body.

This is acceptable: the real API call cannot be tested without a live Massive API key. The important behaviors (timestamp conversion, error handling, malformed responses) are all covered through the mock. A note in a test docstring acknowledging this intentional gap would be helpful.

---

## Strengths

**Architecture:** Clean separation between `GBMSimulator` (pure math, no I/O) and `SimulatorDataSource` (asyncio wrapper). This makes the math testable synchronously without asyncio complexity.

**Factory pattern:** `create_market_data_source` is the only place the concrete classes are referenced. All downstream code types against `MarketDataSource`. Switching data sources requires only an env var change.

**`PriceCache` design:** Thread-safe with a `version` counter is elegant. The SSE stream can detect changes without comparing full payloads, and multiple readers can snapshot the cache without locking each other out.

**Error resilience:** The simulator loop catches and logs all exceptions — a single bad tick cannot kill the stream. The Massive poller logs and continues on 401, 429, and network failures. The conftest stub for the `massive` package is clean and enables the full test suite to run without the optional dependency.

**Lazy imports:** `MassiveDataSource` only imports the `massive` package in `start()` and `_fetch_snapshots()`, not at module import time. This means the package is not required when using the simulator, keeping the default installation light.

**`frozen=True, slots=True` on `PriceUpdate`:** Correct use of `slots=True` for a hot-path dataclass that is created thousands of times per minute. Reduces memory overhead and prevents accidental mutation.

**Test coverage of edge cases:** The tests cover the meaningful edge cases: zero previous price in `change_percent`, removing a nonexistent ticker, empty-ticker step, duplicate add, custom timestamps, whitespace/case normalization in Massive ticker input.

---

## Recommended Actions (Priority Order)

1. **Add SSE stream tests** — `stream.py` at 33% is the largest gap. Tests for `_generate_events` are straightforward to write with `AsyncMock` for the request object.
2. **Add keepalive to SSE loop** — one-line fix; important for Massive mode with 15s poll intervals.
3. **Seed cache immediately on `MassiveDataSource.add_ticker`** — aligns behavior with the simulator path; prevents a 15s price gap after adding a ticker.
4. **Increment `version` in `cache.remove()`** — ensures removals are reflected in the SSE stream immediately.
5. **Replace private-attribute assertions in tests** — use `get_tickers()` and observable behavior.
6. **Clarify TSLA / `CROSS_GROUP_CORR` constants** — add a comment or consolidate the duplicate value.
