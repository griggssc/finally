"""Unit tests for LLM integration."""
import os

import pytest

from app.llm.models import LLMResponse, TradeRequest, WatchlistChange


class TestLLMModels:
    def test_llm_response_parses_from_dict(self):
        data = {
            "message": "Here is my analysis.",
            "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 10}],
            "watchlist_changes": [{"ticker": "PYPL", "action": "add"}],
        }
        resp = LLMResponse(**data)
        assert resp.message == "Here is my analysis."
        assert len(resp.trades) == 1
        assert resp.trades[0].ticker == "AAPL"
        assert resp.trades[0].side == "buy"
        assert resp.trades[0].quantity == 10
        assert len(resp.watchlist_changes) == 1
        assert resp.watchlist_changes[0].ticker == "PYPL"
        assert resp.watchlist_changes[0].action == "add"

    def test_llm_response_defaults_empty_lists(self):
        resp = LLMResponse(message="Hello")
        assert resp.trades == []
        assert resp.watchlist_changes == []

    def test_trade_request_fields(self):
        t = TradeRequest(ticker="TSLA", side="sell", quantity=5.5)
        assert t.ticker == "TSLA"
        assert t.side == "sell"
        assert t.quantity == 5.5

    def test_watchlist_change_fields(self):
        w = WatchlistChange(ticker="NFLX", action="remove")
        assert w.ticker == "NFLX"
        assert w.action == "remove"


class TestMockLLM:
    def test_mock_returns_deterministic_response(self, monkeypatch):
        monkeypatch.setenv("LLM_MOCK", "true")
        from app.llm.client import call_llm
        resp = call_llm("Cash: $10000", [], "How am I doing?")
        assert "Mock response" in resp.message
        assert resp.trades == []
        assert resp.watchlist_changes == []

    def test_mock_includes_user_message(self, monkeypatch):
        monkeypatch.setenv("LLM_MOCK", "true")
        from app.llm.client import call_llm
        resp = call_llm("", [], "Buy AAPL please")
        assert "Buy AAPL please" in resp.message
