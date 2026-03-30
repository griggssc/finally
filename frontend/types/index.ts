export interface PriceUpdate {
  ticker: string
  price: number
  prev_price: number
  change: number
  change_percent: number
  direction: 'up' | 'down' | 'flat'
  timestamp: string
}

export interface Position {
  ticker: string
  quantity: number
  avg_cost: number
  current_price: number
  unrealized_pnl: number
  pnl_percent: number
}

export interface Portfolio {
  cash_balance: number
  total_value: number
  positions: Position[]
}

export interface HistoryPoint {
  total_value: number
  recorded_at: string
}

export interface WatchlistItem {
  ticker: string
  price?: number
  change_percent?: number
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  actions?: {
    trades?: Array<{
      ticker: string
      side: 'buy' | 'sell'
      quantity: number
      price: number
      status: 'executed' | 'failed'
      error?: string
    }>
    watchlist_changes?: Array<{
      ticker: string
      action: 'add' | 'remove'
      status: 'executed' | 'failed'
    }>
  }
  created_at: string
}

export type ConnectionStatus = 'connected' | 'reconnecting' | 'disconnected'
