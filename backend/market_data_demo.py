"""Rich terminal demo for the FinAlly market data simulator.

Self-contained — no FastAPI required. Run with:
    python3 market_data_demo.py
or:
    uv run market_data_demo.py
"""

import collections
import math
import random
import time
from datetime import datetime

import numpy as np
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# ── Inline GBM simulator (no FastAPI dependency) ─────────────────────────────

SEED_PRICES = {
    "AAPL": 190.00, "GOOGL": 175.00, "MSFT": 420.00, "AMZN": 185.00,
    "TSLA": 250.00, "NVDA": 800.00, "META": 500.00, "JPM": 195.00,
    "V": 280.00, "NFLX": 600.00,
}
TICKER_PARAMS = {
    "AAPL":  {"mu": 0.12, "sigma": 0.22},
    "GOOGL": {"mu": 0.14, "sigma": 0.24},
    "MSFT":  {"mu": 0.13, "sigma": 0.20},
    "AMZN":  {"mu": 0.15, "sigma": 0.26},
    "TSLA":  {"mu": 0.10, "sigma": 0.55},
    "NVDA":  {"mu": 0.25, "sigma": 0.45},
    "META":  {"mu": 0.18, "sigma": 0.30},
    "JPM":   {"mu": 0.10, "sigma": 0.18},
    "V":     {"mu": 0.11, "sigma": 0.16},
    "NFLX":  {"mu": 0.16, "sigma": 0.35},
}
DEFAULT_PARAMS = {"mu": 0.10, "sigma": 0.25}
TRADING_SECONDS_PER_YEAR = 252 * 6.5 * 3600
DT = 0.5 / TRADING_SECONDS_PER_YEAR  # one 500ms tick

TECH    = {"AAPL", "GOOGL", "MSFT", "AMZN", "NVDA", "META", "NFLX"}
FINANCE = {"JPM", "V"}


class GBMSimulator:
    """Geometric Brownian Motion price simulator with correlated tickers."""

    def __init__(self, tickers: list[str], event_prob: float = 0.001) -> None:
        self._tickers = list(tickers)
        self._event_prob = event_prob
        self._prices = {t: SEED_PRICES.get(t, random.uniform(50, 300)) for t in tickers}
        self._params = {t: TICKER_PARAMS.get(t, dict(DEFAULT_PARAMS)) for t in tickers}
        self._chol = self._build_cholesky()

    def step(self) -> dict[str, tuple[float, bool]]:
        """Return {ticker: (new_price, is_shock)} for one 500ms tick."""
        n = len(self._tickers)
        z = self._chol @ np.random.standard_normal(n) if self._chol is not None else np.random.standard_normal(n)
        result: dict[str, tuple[float, bool]] = {}
        for i, ticker in enumerate(self._tickers):
            p = self._params[ticker]
            mu, sigma = p["mu"], p["sigma"]
            drift = (mu - 0.5 * sigma ** 2) * DT
            diffusion = sigma * math.sqrt(DT) * z[i]
            self._prices[ticker] *= math.exp(drift + diffusion)
            shock = False
            if random.random() < self._event_prob:
                mag = random.uniform(0.02, 0.05) * random.choice([-1, 1])
                self._prices[ticker] *= 1 + mag
                shock = True
            result[ticker] = (round(self._prices[ticker], 2), shock)
        return result

    def price(self, ticker: str) -> float:
        return self._prices[ticker]

    def _build_cholesky(self) -> np.ndarray | None:
        n = len(self._tickers)
        if n <= 1:
            return None
        corr = np.eye(n)
        for i in range(n):
            for j in range(i + 1, n):
                rho = self._correlate(self._tickers[i], self._tickers[j])
                corr[i, j] = corr[j, i] = rho
        return np.linalg.cholesky(corr)

    @staticmethod
    def _correlate(a: str, b: str) -> float:
        if a == "TSLA" or b == "TSLA":
            return 0.30
        if a in TECH and b in TECH:
            return 0.60
        if a in FINANCE and b in FINANCE:
            return 0.50
        return 0.30


# ── Terminal rendering ────────────────────────────────────────────────────────

TICKERS    = list(SEED_PRICES.keys())
SPARK_CHARS = " ▁▂▃▄▅▆▇█"
SPARK_WIDTH = 22
HISTORY_LEN = 60
LOG_LINES   = 12


def sparkline(prices: list[float]) -> str:
    data = list(prices)[-SPARK_WIDTH:]
    if len(data) < 2:
        return "─" * SPARK_WIDTH
    lo, hi = min(data), max(data)
    if hi == lo:
        return "─" * len(data)
    idxs = [int((p - lo) / (hi - lo) * (len(SPARK_CHARS) - 1)) for p in data]
    return "".join(SPARK_CHARS[i] for i in idxs).ljust(SPARK_WIDTH)


def spark_style(prices: collections.deque) -> str:
    lst = list(prices)
    return "green" if len(lst) < 2 or lst[-1] >= lst[0] else "red"


def price_table(
    prices: dict[str, float],
    opens: dict[str, float],
    prev: dict[str, float],
    hists: dict[str, collections.deque],
) -> Table:
    t = Table(
        show_header=True,
        header_style="bold #ecad0a",
        border_style="bright_black",
        pad_edge=False,
        expand=True,
    )
    t.add_column("Ticker",    style="bold white",  width=7,            no_wrap=True)
    t.add_column("Price",     justify="right",      width=11,           no_wrap=True)
    t.add_column("",          justify="center",     width=2,            no_wrap=True)  # arrow
    t.add_column("Tick Δ",    justify="right",      width=8,            no_wrap=True)
    t.add_column("Day %",     justify="right",      width=8,            no_wrap=True)
    t.add_column("Sparkline", width=SPARK_WIDTH + 1, no_wrap=True)

    for ticker in TICKERS:
        price      = prices[ticker]
        last       = prev[ticker]
        open_price = opens[ticker]
        tick_chg   = price - last
        day_pct    = (price - open_price) / open_price * 100 if open_price else 0.0

        if tick_chg > 0:
            arrow, color = "▲", "green"
        elif tick_chg < 0:
            arrow, color = "▼", "red"
        else:
            arrow, color = "─", "bright_black"

        day_color = "green" if day_pct >= 0 else "red"

        t.add_row(
            ticker,
            Text(f"${price:>9,.2f}",          style=f"bold {color}"),
            Text(arrow,                         style=color),
            Text(f"{tick_chg:+.3f}",           style=color),
            Text(f"{day_pct:+.2f}%",           style=day_color),
            Text(sparkline(hists[ticker]),      style=spark_style(hists[ticker])),
        )
    return t


def event_panel(events: list[str]) -> Panel:
    text = Text()
    for line in events[-LOG_LINES:]:
        text.append_text(Text.from_markup(line + "\n"))
    return Panel(text, title="[bold #ecad0a]Event Log", border_style="#753991", padding=(0, 1))


def render(
    prices: dict[str, float],
    opens: dict[str, float],
    prev: dict[str, float],
    hists: dict[str, collections.deque],
    events: list[str],
    tick: int,
) -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="hdr", size=3),
        Layout(name="body"),
        Layout(name="log", size=LOG_LINES + 2),
    )
    ts = datetime.now().strftime("%H:%M:%S")
    layout["hdr"].update(
        Panel(
            f"[bold #ecad0a]FinAlly[/] — Market Data Demo   "
            f"[dim]{ts}[/]   [dim]tick #{tick}[/]",
            border_style="#209dd7",
        )
    )
    layout["body"].update(
        Panel(
            price_table(prices, opens, prev, hists),
            title="[bold #209dd7]Live Prices",
            border_style="#209dd7",
            padding=(0, 1),
        )
    )
    layout["log"].update(event_panel(events))
    return layout


# ── Main loop ─────────────────────────────────────────────────────────────────

def run(interval: float = 0.5) -> None:
    # Elevated shock prob so the event log fills quickly in a demo
    sim = GBMSimulator(TICKERS, event_prob=0.05)

    prices: dict[str, float] = {t: sim.price(t) for t in TICKERS}
    opens:  dict[str, float] = dict(prices)
    prev:   dict[str, float] = dict(prices)
    hists:  dict[str, collections.deque] = {
        t: collections.deque([prices[t]], maxlen=HISTORY_LEN) for t in TICKERS
    }
    events: list[str] = []
    tick = 0

    console = Console()

    with Live(render(prices, opens, prev, hists, events, tick),
              console=console, refresh_per_second=4, screen=True) as live:
        try:
            while True:
                updates = sim.step()
                tick += 1
                ts = datetime.now().strftime("%H:%M:%S")

                for ticker, (new_price, shock) in updates.items():
                    old_price = prices[ticker]
                    chg_pct   = (new_price - old_price) / old_price * 100 if old_price else 0.0
                    color     = "green" if chg_pct >= 0 else "red"
                    sign      = "+" if chg_pct >= 0 else ""

                    if shock:
                        label = "[bold]SHOCK[/bold]"
                        events.append(
                            f"[{color}][{ts}] {ticker:<5} {label}  "
                            f"${old_price:.2f} → ${new_price:.2f}  ({sign}{chg_pct:.2f}%)[/{color}]"
                        )
                    elif abs(chg_pct) >= 0.8:
                        events.append(
                            f"[{color}][{ts}] {ticker:<5} notable  "
                            f"${old_price:.2f} → ${new_price:.2f}  ({sign}{chg_pct:.2f}%)[/{color}]"
                        )

                    prev[ticker]  = old_price
                    prices[ticker] = new_price
                    hists[ticker].append(new_price)

                live.update(render(prices, opens, prev, hists, events, tick))
                time.sleep(interval)

        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    run()
