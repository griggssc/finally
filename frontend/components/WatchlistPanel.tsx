'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import Sparkline from './Sparkline'
import type { PriceUpdate, WatchlistItem } from '@/types'

interface WatchlistPanelProps {
  prices: Map<string, PriceUpdate>
  selectedTicker: string
  onSelectTicker: (ticker: string) => void
}

const MAX_SPARKLINE_POINTS = 300

export default function WatchlistPanel({
  prices,
  selectedTicker,
  onSelectTicker,
}: WatchlistPanelProps) {
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([])
  const [addInput, setAddInput] = useState('')
  const [adding, setAdding] = useState(false)
  const sparklineDataRef = useRef<Map<string, number[]>>(new Map())
  const [, forceUpdate] = useState(0)
  const flashRef = useRef<Map<string, 'up' | 'down'>>(new Map())
  const prevPricesRef = useRef<Map<string, number>>(new Map())

  const fetchWatchlist = useCallback(async () => {
    try {
      const res = await fetch('/api/watchlist')
      if (res.ok) {
        const data = await res.json()
        setWatchlist(data)
      }
    } catch {
      // ignore
    }
  }, [])

  useEffect(() => {
    fetchWatchlist()
  }, [fetchWatchlist])

  // Update sparkline data and flash state when prices change
  useEffect(() => {
    let changed = false
    for (const [ticker, update] of prices.entries()) {
      const prev = prevPricesRef.current.get(ticker)
      if (prev === update.price) continue
      changed = true

      // Flash direction
      if (prev !== undefined) {
        flashRef.current.set(ticker, update.price > prev ? 'up' : 'down')
        setTimeout(() => {
          flashRef.current.delete(ticker)
          forceUpdate(n => n + 1)
        }, 500)
      }

      prevPricesRef.current.set(ticker, update.price)

      // Sparkline
      const arr = sparklineDataRef.current.get(ticker) ?? []
      arr.push(update.price)
      if (arr.length > MAX_SPARKLINE_POINTS) arr.shift()
      sparklineDataRef.current.set(ticker, arr)
    }
    if (changed) forceUpdate(n => n + 1)
  }, [prices])

  const handleAdd = async () => {
    const ticker = addInput.trim().toUpperCase()
    if (!ticker) return
    setAdding(true)
    try {
      const res = await fetch('/api/watchlist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker }),
      })
      if (res.ok) {
        setAddInput('')
        await fetchWatchlist()
      }
    } finally {
      setAdding(false)
    }
  }

  const handleRemove = async (ticker: string) => {
    try {
      await fetch(`/api/watchlist/${ticker}`, { method: 'DELETE' })
      await fetchWatchlist()
    } catch {
      // ignore
    }
  }

  return (
    <div className="flex flex-col h-full bg-panel">
      <div className="px-3 py-2 border-b border-border flex items-center justify-between">
        <span className="text-text-muted text-xs uppercase tracking-wider font-bold">Watchlist</span>
      </div>

      <div className="flex-1 overflow-y-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-text-muted border-b border-border">
              <th className="text-left px-2 py-1">Ticker</th>
              <th className="text-right px-2 py-1">Price</th>
              <th className="text-right px-2 py-1">Chg%</th>
              <th className="text-right px-1 py-1"></th>
              <th className="w-4"></th>
            </tr>
          </thead>
          <tbody>
            {watchlist.map(item => {
              const live = prices.get(item.ticker)
              const price = live?.price ?? item.price
              const changePct = live?.change_percent ?? item.change_percent ?? 0
              const flash = flashRef.current.get(item.ticker)
              const sparkData = sparklineDataRef.current.get(item.ticker) ?? []

              return (
                <tr
                  key={item.ticker}
                  onClick={() => onSelectTicker(item.ticker)}
                  className={`
                    cursor-pointer border-b border-border/50 transition-colors
                    ${selectedTicker === item.ticker ? 'bg-panel-light' : 'hover:bg-panel-light/50'}
                    ${flash === 'up' ? 'price-flash-up' : flash === 'down' ? 'price-flash-down' : ''}
                  `}
                >
                  <td className="px-2 py-1.5">
                    <span className={`font-bold ${selectedTicker === item.ticker ? 'text-accent' : 'text-text-primary'}`}>
                      {item.ticker}
                    </span>
                  </td>
                  <td className="px-2 py-1.5 text-right font-mono">
                    {price != null ? `$${price.toFixed(2)}` : '--'}
                  </td>
                  <td className={`px-2 py-1.5 text-right font-mono ${changePct >= 0 ? 'text-price-up' : 'text-price-down'}`}>
                    {changePct >= 0 ? '+' : ''}{changePct.toFixed(2)}%
                  </td>
                  <td className="px-1 py-1.5 text-right">
                    <Sparkline data={sparkData} width={48} height={20} />
                  </td>
                  <td className="pr-2">
                    <button
                      onClick={e => { e.stopPropagation(); handleRemove(item.ticker) }}
                      className="text-text-muted hover:text-price-down transition-colors leading-none"
                    >
                      x
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="p-2 border-t border-border flex gap-1">
        <input
          type="text"
          value={addInput}
          onChange={e => setAddInput(e.target.value.toUpperCase())}
          onKeyDown={e => e.key === 'Enter' && handleAdd()}
          placeholder="Add ticker..."
          className="flex-1 bg-background border border-border rounded px-2 py-1 text-xs text-text-primary placeholder-text-muted outline-none focus:border-primary"
          maxLength={10}
        />
        <button
          onClick={handleAdd}
          disabled={adding || !addInput.trim()}
          className="px-2 py-1 bg-secondary text-white rounded text-xs hover:opacity-90 disabled:opacity-50 transition-opacity"
        >
          +
        </button>
      </div>
    </div>
  )
}
