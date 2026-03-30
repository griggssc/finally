"""Tests for the SSE streaming generator (_generate_events)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from app.market.cache import PriceCache
from app.market.stream import _generate_events


def _make_request(disconnected_sequence: list[bool]) -> AsyncMock:
    """Build a mock FastAPI Request.

    disconnected_sequence: list of return values for successive
    is_disconnected() calls. The generator checks once per loop
    iteration, so the final True causes it to break.
    """
    request = AsyncMock()
    request.client = None  # Avoids AttributeError on request.client.host
    request.is_disconnected = AsyncMock(side_effect=disconnected_sequence)
    return request


async def _collect(cache: PriceCache, request: AsyncMock, max_events: int = 20) -> list[str]:
    """Collect up to max_events from _generate_events."""
    events: list[str] = []
    async for event in _generate_events(cache, request, interval=0.001):
        events.append(event)
        if len(events) >= max_events:
            break
    return events


@pytest.mark.asyncio
class TestGenerateEvents:
    async def test_retry_directive_is_first_event(self):
        """The first yielded event must be the SSE retry directive."""
        cache = PriceCache()
        request = _make_request([False, True])

        events = await _collect(cache, request)

        assert events[0] == "retry: 1000\n\n"

    async def test_price_event_emitted_on_cache_update(self):
        """A data event is sent when the cache has content and the version changed."""
        cache = PriceCache()
        cache.update("AAPL", 190.50)
        request = _make_request([False, True])

        events = await _collect(cache, request)

        data_events = [e for e in events if e.startswith("data:")]
        assert len(data_events) == 1
        payload = json.loads(data_events[0].removeprefix("data: ").strip())
        assert "AAPL" in payload
        assert payload["AAPL"]["price"] == 190.50

    async def test_empty_cache_sends_no_data_event(self):
        """When the cache is empty, no data: event should be emitted."""
        cache = PriceCache()
        request = _make_request([False, True])

        events = await _collect(cache, request)

        data_events = [e for e in events if e.startswith("data:")]
        assert data_events == []

    async def test_keepalive_sent_when_no_change(self):
        """When the cache version is unchanged, a keepalive comment is yielded."""
        cache = PriceCache()
        cache.update("AAPL", 190.00)

        # First iteration: version changed → data event
        # Second iteration: version unchanged → keepalive
        # Third iteration: disconnect
        request = _make_request([False, False, True])

        events = await _collect(cache, request)

        keepalives = [e for e in events if e == ": keepalive\n\n"]
        assert len(keepalives) >= 1

    async def test_disconnect_terminates_generator(self):
        """Generator should stop cleanly when client disconnects."""
        cache = PriceCache()
        request = _make_request([True])  # Disconnect on the very first check

        events = await _collect(cache, request)

        # Only the initial retry directive is yielded before the loop starts
        assert events == ["retry: 1000\n\n"]

    async def test_multiple_tickers_in_event(self):
        """All tickers in the cache appear in a single SSE data event."""
        cache = PriceCache()
        cache.update("AAPL", 190.00)
        cache.update("GOOGL", 175.00)
        request = _make_request([False, True])

        events = await _collect(cache, request)

        data_events = [e for e in events if e.startswith("data:")]
        assert len(data_events) == 1
        payload = json.loads(data_events[0].removeprefix("data: ").strip())
        assert "AAPL" in payload
        assert "GOOGL" in payload

    async def test_cache_removal_triggers_event(self):
        """Removing a ticker bumps the cache version and triggers a new data event."""
        cache = PriceCache()
        cache.update("AAPL", 190.00)
        cache.update("GOOGL", 175.00)

        # Allow three loop iterations: first sends both tickers,
        # then we remove GOOGL (bumping version), second sends only AAPL.
        request = _make_request([False, False, True])

        events: list[str] = []
        iteration = 0
        async for event in _generate_events(cache, request, interval=0.001):
            events.append(event)
            # After the first data event, remove GOOGL so version bumps
            if event.startswith("data:") and iteration == 0:
                cache.remove("GOOGL")
                iteration += 1
            if len(events) >= 10:
                break

        data_events = [e for e in events if e.startswith("data:")]
        assert len(data_events) >= 2
        last_payload = json.loads(data_events[-1].removeprefix("data: ").strip())
        assert "GOOGL" not in last_payload
        assert "AAPL" in last_payload
