'use client'

import type { ConnectionStatus } from '@/types'

interface HeaderProps {
  totalValue: number
  cashBalance: number
  connectionStatus: ConnectionStatus
  onToggleChat: () => void
  chatOpen: boolean
}

const statusColors: Record<ConnectionStatus, string> = {
  connected: 'bg-green-500',
  reconnecting: 'bg-yellow-400',
  disconnected: 'bg-red-500',
}

const statusLabels: Record<ConnectionStatus, string> = {
  connected: 'Live',
  reconnecting: 'Reconnecting',
  disconnected: 'Offline',
}

export default function Header({
  totalValue,
  cashBalance,
  connectionStatus,
  onToggleChat,
  chatOpen,
}: HeaderProps) {
  const pnl = totalValue - 10000

  return (
    <header className="flex items-center justify-between px-4 py-2 bg-panel border-b border-border flex-shrink-0">
      <div className="flex items-center gap-3">
        <span className="text-accent font-bold text-lg tracking-widest uppercase">
          Fin<span className="text-primary">Ally</span>
        </span>
        <span className="text-text-muted text-xs">AI Trading Workstation</span>
      </div>

      <div className="flex items-center gap-6">
        <div className="text-center">
          <div className="text-text-muted text-xs uppercase tracking-wider">Portfolio</div>
          <div className="text-text-primary font-bold text-base">
            ${totalValue.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
        </div>

        <div className="text-center">
          <div className="text-text-muted text-xs uppercase tracking-wider">P&amp;L</div>
          <div className={`font-bold text-base ${pnl >= 0 ? 'text-price-up' : 'text-price-down'}`}>
            {pnl >= 0 ? '+' : ''}${pnl.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
        </div>

        <div className="text-center">
          <div className="text-text-muted text-xs uppercase tracking-wider">Cash</div>
          <div className="text-accent font-bold text-base">
            ${cashBalance.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${statusColors[connectionStatus]} shadow-sm`}
            style={connectionStatus === 'connected' ? { boxShadow: '0 0 6px #22c55e' } : {}} />
          <span className="text-text-muted text-xs">{statusLabels[connectionStatus]}</span>
        </div>

        <button
          onClick={onToggleChat}
          className="text-xs px-2 py-1 border border-border rounded text-text-secondary hover:text-primary hover:border-primary transition-colors"
        >
          {chatOpen ? 'Hide Chat' : 'AI Chat'}
        </button>
      </div>
    </header>
  )
}
