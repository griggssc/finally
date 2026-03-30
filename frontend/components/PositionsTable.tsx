'use client'

import type { Portfolio, PriceUpdate } from '@/types'

interface PositionsTableProps {
  portfolio: Portfolio | null
  prices: Map<string, PriceUpdate>
}

export default function PositionsTable({ portfolio, prices }: PositionsTableProps) {
  if (!portfolio?.positions.length) {
    return (
      <div className="bg-panel">
        <div className="px-3 py-1.5 border-b border-border">
          <span className="text-text-muted text-xs uppercase tracking-wider font-bold">Positions</span>
        </div>
        <div className="px-3 py-3 text-text-muted text-xs">No open positions</div>
      </div>
    )
  }

  return (
    <div className="bg-panel">
      <div className="px-3 py-1.5 border-b border-border">
        <span className="text-text-muted text-xs uppercase tracking-wider font-bold">Positions</span>
      </div>
      <table className="w-full text-xs">
        <thead>
          <tr className="text-text-muted border-b border-border">
            <th className="text-left px-3 py-1">Ticker</th>
            <th className="text-right px-3 py-1">Qty</th>
            <th className="text-right px-3 py-1">Avg Cost</th>
            <th className="text-right px-3 py-1">Price</th>
            <th className="text-right px-3 py-1">Unrealized P&amp;L</th>
            <th className="text-right px-3 py-1">P&amp;L %</th>
          </tr>
        </thead>
        <tbody>
          {portfolio.positions.map(pos => {
            const livePrice = prices.get(pos.ticker)?.price ?? pos.current_price
            const unrealizedPnl = (livePrice - pos.avg_cost) * pos.quantity
            const pnlPct = pos.avg_cost > 0 ? ((livePrice - pos.avg_cost) / pos.avg_cost) * 100 : 0
            const positive = unrealizedPnl >= 0

            return (
              <tr key={pos.ticker} className="border-b border-border/50 hover:bg-panel-light/50 transition-colors">
                <td className="px-3 py-1.5 text-accent font-bold">{pos.ticker}</td>
                <td className="px-3 py-1.5 text-right text-text-primary font-mono">{pos.quantity}</td>
                <td className="px-3 py-1.5 text-right text-text-secondary font-mono">${pos.avg_cost.toFixed(2)}</td>
                <td className="px-3 py-1.5 text-right text-text-primary font-mono">${livePrice.toFixed(2)}</td>
                <td className={`px-3 py-1.5 text-right font-mono font-bold ${positive ? 'text-price-up' : 'text-price-down'}`}>
                  {positive ? '+' : ''}${unrealizedPnl.toFixed(2)}
                </td>
                <td className={`px-3 py-1.5 text-right font-mono ${positive ? 'text-price-up' : 'text-price-down'}`}>
                  {positive ? '+' : ''}{pnlPct.toFixed(2)}%
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
