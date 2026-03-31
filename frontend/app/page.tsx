'use client'

import { useState, useEffect, useCallback } from 'react'
import Header from '@/components/Header'
import WatchlistPanel from '@/components/WatchlistPanel'
import MainChart from '@/components/MainChart'
import PortfolioHeatmap from '@/components/PortfolioHeatmap'
import PnLChart from '@/components/PnLChart'
import PositionsTable from '@/components/PositionsTable'
import TradeBar from '@/components/TradeBar'
import ChatPanel from '@/components/ChatPanel'
import { usePriceStream } from '@/hooks/usePriceStream'
import type { Portfolio, HistoryPoint } from '@/types'

export default function Home() {
  const { prices, status } = usePriceStream()
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null)
  const [history, setHistory] = useState<HistoryPoint[]>([])
  const [selectedTicker, setSelectedTicker] = useState<string>('AAPL')
  const [chatOpen, setChatOpen] = useState(true)
  const [watchlistRefreshKey, setWatchlistRefreshKey] = useState(0)

  const fetchPortfolio = useCallback(async () => {
    try {
      const res = await fetch('/api/portfolio')
      if (res.ok) setPortfolio(await res.json())
    } catch {
      // silently ignore transient errors
    }
  }, [])

  const fetchHistory = useCallback(async () => {
    try {
      const res = await fetch('/api/portfolio/history')
      if (res.ok) setHistory(await res.json())
    } catch {
      // silently ignore
    }
  }, [])

  useEffect(() => {
    fetchPortfolio()
    fetchHistory()
    const portfolioInterval = setInterval(fetchPortfolio, 5000)
    const historyInterval = setInterval(fetchHistory, 30000)
    return () => {
      clearInterval(portfolioInterval)
      clearInterval(historyInterval)
    }
  }, [fetchPortfolio, fetchHistory])

  const handleTradeComplete = (hasWatchlistChanges = false) => {
    fetchPortfolio()
    fetchHistory()
    if (hasWatchlistChanges) setWatchlistRefreshKey(k => k + 1)
  }

  // Compute live total value using SSE prices
  const liveTotalValue = portfolio
    ? portfolio.cash_balance +
      portfolio.positions.reduce((sum, pos) => {
        const live = prices.get(pos.ticker)
        const price = live?.price ?? pos.current_price
        return sum + pos.quantity * price
      }, 0)
    : 0

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-background">
      <Header
        totalValue={liveTotalValue}
        cashBalance={portfolio?.cash_balance ?? 0}
        connectionStatus={status}
        onToggleChat={() => setChatOpen(o => !o)}
        chatOpen={chatOpen}
      />

      <div className="flex flex-1 overflow-hidden">
        {/* Left: Watchlist */}
        <div className="w-64 flex-shrink-0 border-r border-border overflow-y-auto">
          <WatchlistPanel
            prices={prices}
            selectedTicker={selectedTicker}
            onSelectTicker={setSelectedTicker}
            refreshKey={watchlistRefreshKey}
          />
        </div>

        {/* Center: Main content */}
        <div className="flex-1 flex flex-col overflow-hidden min-w-0">
          {/* Top: Chart */}
          <div className="flex-1 border-b border-border min-h-0" style={{ minHeight: '220px', maxHeight: '340px' }}>
            <MainChart ticker={selectedTicker} prices={prices} />
          </div>

          {/* Middle: Heatmap + P&L */}
          <div className="flex border-b border-border" style={{ height: '180px' }}>
            <div className="flex-1 border-r border-border min-w-0">
              <PortfolioHeatmap portfolio={portfolio} prices={prices} />
            </div>
            <div className="flex-1 min-w-0">
              <PnLChart history={history} />
            </div>
          </div>

          {/* Bottom: Positions + Trade */}
          <div className="flex flex-col overflow-hidden" style={{ height: '220px' }}>
            <div className="flex-1 overflow-y-auto min-h-0">
              <PositionsTable portfolio={portfolio} prices={prices} />
            </div>
            <div className="flex-shrink-0 border-t border-border">
              <TradeBar onTradeComplete={handleTradeComplete} prices={prices} />
            </div>
          </div>
        </div>

        {/* Right: Chat Panel */}
        {chatOpen && (
          <div className="w-80 flex-shrink-0 border-l border-border flex flex-col overflow-hidden">
            <ChatPanel onTradeComplete={handleTradeComplete} />
          </div>
        )}
      </div>
    </div>
  )
}
