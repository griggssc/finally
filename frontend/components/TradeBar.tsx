'use client'

import { useState } from 'react'
import type { PriceUpdate } from '@/types'

interface TradeBarProps {
  onTradeComplete: () => void
  prices: Map<string, PriceUpdate>
}

export default function TradeBar({ onTradeComplete, prices }: TradeBarProps) {
  const [ticker, setTicker] = useState('')
  const [quantity, setQuantity] = useState('')
  const [loading, setLoading] = useState(false)
  const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null)

  const showToast = (msg: string, ok: boolean) => {
    setToast({ msg, ok })
    setTimeout(() => setToast(null), 3000)
  }

  const executeTrade = async (side: 'buy' | 'sell') => {
    const t = ticker.trim().toUpperCase()
    const q = parseFloat(quantity)
    if (!t || !q || q <= 0) {
      showToast('Enter a valid ticker and quantity', false)
      return
    }

    setLoading(true)
    try {
      const res = await fetch('/api/portfolio/trade', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker: t, quantity: q, side }),
      })
      const data = await res.json()
      if (res.ok) {
        const price = data.price ?? prices.get(t)?.price
        const priceStr = price ? ` @ $${Number(price).toFixed(2)}` : ''
        showToast(`${side === 'buy' ? 'Bought' : 'Sold'} ${q} ${t}${priceStr}`, true)
        setQuantity('')
        onTradeComplete()
      } else {
        showToast(data.detail ?? data.error ?? 'Trade failed', false)
      }
    } catch {
      showToast('Network error', false)
    } finally {
      setLoading(false)
    }
  }

  const currentPrice = prices.get(ticker.toUpperCase())

  return (
    <div className="flex items-center gap-2 px-3 py-2 bg-panel">
      <span className="text-text-muted text-xs uppercase tracking-wider whitespace-nowrap">Trade</span>

      <input
        type="text"
        value={ticker}
        onChange={e => setTicker(e.target.value.toUpperCase())}
        placeholder="Ticker"
        className="w-20 bg-background border border-border rounded px-2 py-1 text-xs text-text-primary placeholder-text-muted outline-none focus:border-primary font-mono uppercase"
        maxLength={10}
      />

      <input
        type="number"
        value={quantity}
        onChange={e => setQuantity(e.target.value)}
        placeholder="Qty"
        step="0.1"
        min="0"
        className="w-20 bg-background border border-border rounded px-2 py-1 text-xs text-text-primary placeholder-text-muted outline-none focus:border-primary font-mono"
      />

      {currentPrice && (
        <span className="text-text-muted text-xs font-mono whitespace-nowrap">
          ${currentPrice.price.toFixed(2)}
        </span>
      )}

      <button
        onClick={() => executeTrade('buy')}
        disabled={loading}
        className="px-3 py-1 bg-primary text-white rounded text-xs font-bold hover:opacity-90 disabled:opacity-50 transition-opacity"
      >
        BUY
      </button>

      <button
        onClick={() => executeTrade('sell')}
        disabled={loading}
        className="px-3 py-1 bg-price-down text-white rounded text-xs font-bold hover:opacity-90 disabled:opacity-50 transition-opacity"
      >
        SELL
      </button>

      {toast && (
        <span className={`text-xs ml-2 animate-fade-in ${toast.ok ? 'text-price-up' : 'text-price-down'}`}>
          {toast.msg}
        </span>
      )}
    </div>
  )
}
