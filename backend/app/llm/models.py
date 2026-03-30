"""Pydantic schemas for LLM structured output."""
from pydantic import BaseModel


class TradeRequest(BaseModel):
    ticker: str
    side: str  # "buy" or "sell"
    quantity: float


class WatchlistChange(BaseModel):
    ticker: str
    action: str  # "add" or "remove"


class LLMResponse(BaseModel):
    message: str
    trades: list[TradeRequest] = []
    watchlist_changes: list[WatchlistChange] = []
