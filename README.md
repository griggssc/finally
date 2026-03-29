# FinAlly — AI Trading Workstation

An AI-powered trading workstation that streams live market prices, lets you trade a simulated portfolio, and includes an LLM chat assistant that can analyze positions and execute trades on your behalf.

## Quick Start

```bash
cp .env.example .env
# Add your OPENROUTER_API_KEY to .env
./scripts/start_mac.sh   # macOS/Linux
# or: scripts/start_windows.ps1  (Windows PowerShell)
```

Open [http://localhost:8000](http://localhost:8000).

## Features

- Live price streaming via SSE with sparkline charts
- Simulated portfolio — $10,000 starting cash, market orders, instant fill
- Portfolio heatmap (treemap) and P&L history chart
- AI chat assistant — asks questions, analyzes positions, executes trades

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | Yes | LLM chat via OpenRouter (Cerebras inference) |
| `MASSIVE_API_KEY` | No | Real market data; omit to use the built-in simulator |
| `LLM_MOCK` | No | Set `true` for deterministic mock LLM responses (testing) |

## Architecture

Single Docker container on port 8000:

- **Frontend**: Next.js (TypeScript), static export served by FastAPI
- **Backend**: FastAPI (Python/uv), SSE streaming, SQLite, LiteLLM → OpenRouter
- **Market data**: Geometric Brownian Motion simulator (default) or Massive/Polygon.io REST API

## Development

```bash
# Backend
cd backend && uv run uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm install && npm run dev
```

## Testing

```bash
# E2E tests (requires Docker)
docker compose --profile test up
```
# finally
