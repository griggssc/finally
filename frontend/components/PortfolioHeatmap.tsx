'use client'

import { useMemo } from 'react'
import type { Portfolio, PriceUpdate } from '@/types'

interface PortfolioHeatmapProps {
  portfolio: Portfolio | null
  prices: Map<string, PriceUpdate>
}

interface Rect {
  ticker: string
  x: number
  y: number
  w: number
  h: number
  pnlPct: number
}

/** Simple slice-and-dice treemap layout */
function sliceDice(
  items: { ticker: string; value: number; pnlPct: number }[],
  x: number,
  y: number,
  w: number,
  h: number,
  horizontal: boolean
): Rect[] {
  if (!items.length) return []
  const total = items.reduce((s, i) => s + i.value, 0)
  if (total === 0) return []

  const rects: Rect[] = []
  let offset = 0

  for (const item of items) {
    const frac = item.value / total
    if (horizontal) {
      const rw = frac * w
      rects.push({ ticker: item.ticker, x: x + offset, y, w: rw, h, pnlPct: item.pnlPct })
      offset += rw
    } else {
      const rh = frac * h
      rects.push({ ticker: item.ticker, x, y: y + offset, w, h: rh, pnlPct: item.pnlPct })
      offset += rh
    }
  }

  return rects
}

function pnlColor(pct: number): string {
  if (pct > 3) return '#16a34a'
  if (pct > 1) return '#15803d'
  if (pct > 0.1) return '#166534'
  if (pct < -3) return '#dc2626'
  if (pct < -1) return '#b91c1c'
  if (pct < -0.1) return '#991b1b'
  return '#1e3a5f'
}

const W = 400
const H = 140

export default function PortfolioHeatmap({ portfolio, prices }: PortfolioHeatmapProps) {
  const rects = useMemo(() => {
    if (!portfolio?.positions.length) return []

    const items = portfolio.positions
      .map(pos => {
        const livePrice = prices.get(pos.ticker)?.price ?? pos.current_price
        const value = pos.quantity * livePrice
        const pnlPct = pos.avg_cost > 0 ? ((livePrice - pos.avg_cost) / pos.avg_cost) * 100 : 0
        return { ticker: pos.ticker, value, pnlPct }
      })
      .filter(i => i.value > 0)
      .sort((a, b) => b.value - a.value)

    return sliceDice(items, 0, 0, W, H, true)
  }, [portfolio, prices])

  if (!portfolio?.positions.length) {
    return (
      <div className="flex items-center justify-center h-full bg-panel">
        <span className="text-text-muted text-xs">No positions</span>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full bg-panel">
      <div className="px-3 py-1.5 border-b border-border flex-shrink-0">
        <span className="text-text-muted text-xs uppercase tracking-wider font-bold">Portfolio Heatmap</span>
      </div>
      <div className="flex-1 p-1 min-h-0">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="w-full h-full"
          preserveAspectRatio="none"
        >
          {rects.map(rect => (
            <g key={rect.ticker}>
              <rect
                x={rect.x + 1}
                y={rect.y + 1}
                width={Math.max(rect.w - 2, 0)}
                height={Math.max(rect.h - 2, 0)}
                fill={pnlColor(rect.pnlPct)}
                rx="2"
              />
              {rect.w > 30 && rect.h > 16 && (
                <>
                  <text
                    x={rect.x + rect.w / 2}
                    y={rect.y + rect.h / 2 - 5}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    fill="#e6e6e6"
                    fontSize={Math.min(13, rect.w / 4, rect.h / 3)}
                    fontWeight="bold"
                    fontFamily="monospace"
                  >
                    {rect.ticker}
                  </text>
                  <text
                    x={rect.x + rect.w / 2}
                    y={rect.y + rect.h / 2 + 9}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    fill={rect.pnlPct >= 0 ? '#86efac' : '#fca5a5'}
                    fontSize={Math.min(10, rect.w / 5, rect.h / 4)}
                    fontFamily="monospace"
                  >
                    {rect.pnlPct >= 0 ? '+' : ''}{rect.pnlPct.toFixed(1)}%
                  </text>
                </>
              )}
            </g>
          ))}
        </svg>
      </div>
    </div>
  )
}
