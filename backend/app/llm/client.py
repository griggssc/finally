"""LiteLLM client for OpenRouter/Cerebras inference."""
import json
import os

import litellm

from .models import LLMResponse

SYSTEM_PROMPT = """You are FinAlly, an AI trading assistant for a simulated trading workstation.
You help users analyze their portfolio, suggest trades, and execute trades on their behalf.
You have access to real-time portfolio data including positions, P&L, cash balance, and watchlist prices.
Be concise and data-driven. Always respond with valid JSON matching the required schema.
When executing trades, confirm what you did and why.
"""


def build_portfolio_context(portfolio: dict) -> str:
    """Format portfolio data as a human-readable context string."""
    lines = [
        f"Cash: ${portfolio['cash_balance']:.2f}",
        f"Total Value: ${portfolio['total_value']:.2f}",
        "Positions:",
    ]
    for p in portfolio.get("positions", []):
        pnl_sign = "+" if p["unrealized_pnl"] >= 0 else ""
        lines.append(
            f"  {p['ticker']}: {p['quantity']} shares @ ${p['avg_cost']:.2f} avg, "
            f"now ${p['current_price']:.2f}, P&L: {pnl_sign}${p['unrealized_pnl']:.2f} ({pnl_sign}{p['pnl_percent']:.2f}%)"
        )
    return "\n".join(lines)


def call_llm(portfolio_context: str, history: list[dict], user_message: str) -> LLMResponse:
    """Call the LLM and return a structured response.

    Uses LLM_MOCK=true for deterministic testing responses.
    """
    if os.getenv("LLM_MOCK", "false").lower() == "true":
        return _mock_response(user_message)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT + "\n\nCurrent Portfolio:\n" + portfolio_context}
    ]
    for msg in history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_message})

    response = litellm.completion(
        model="openrouter/openai/gpt-oss-120b",
        messages=messages,
        response_format={"type": "json_object"},
        timeout=30,
        api_base="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY"),
    )

    content = response.choices[0].message.content
    data = json.loads(content)
    return LLMResponse(**data)


def _mock_response(message: str) -> LLMResponse:
    return LLMResponse(
        message=f"Mock response to: {message}. Your portfolio looks good!",
        trades=[],
        watchlist_changes=[],
    )
