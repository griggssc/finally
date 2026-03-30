'use client'

import { useState, useRef, useEffect } from 'react'
import type { ChatMessage } from '@/types'

interface ChatPanelProps {
  onTradeComplete: () => void
}

let msgIdCounter = 0
function newId() { return `msg-${++msgIdCounter}` }

export default function ChatPanel({ onTradeComplete }: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: newId(),
      role: 'assistant',
      content: 'Hello, I am FinAlly, your AI trading assistant. Ask me about your portfolio, request analysis, or tell me to execute trades.',
      created_at: new Date().toISOString(),
    },
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const sendMessage = async () => {
    const text = input.trim()
    if (!text || loading) return

    const userMsg: ChatMessage = {
      id: newId(),
      role: 'user',
      content: text,
      created_at: new Date().toISOString(),
    }

    setMessages(prev => [...prev, userMsg])
    setInput('')
    setLoading(true)

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text }),
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' }))
        setMessages(prev => [...prev, {
          id: newId(),
          role: 'assistant',
          content: `Error: ${err.detail ?? 'Request failed'}`,
          created_at: new Date().toISOString(),
        }])
        return
      }

      const data = await res.json()
      const assistantMsg: ChatMessage = {
        id: newId(),
        role: 'assistant',
        content: data.message,
        actions: {
          trades: data.trades,
          watchlist_changes: data.watchlist_changes,
        },
        created_at: new Date().toISOString(),
      }

      setMessages(prev => [...prev, assistantMsg])

      if (data.trades?.length || data.watchlist_changes?.length) {
        onTradeComplete()
      }
    } catch {
      setMessages(prev => [...prev, {
        id: newId(),
        role: 'assistant',
        content: 'Connection error. Please try again.',
        created_at: new Date().toISOString(),
      }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col h-full bg-panel">
      <div className="px-3 py-2 border-b border-border flex-shrink-0">
        <span className="text-accent font-bold text-xs uppercase tracking-wider">AI Assistant</span>
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-2">
        {messages.map(msg => (
          <div key={msg.id} className={`flex flex-col gap-1 ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
            <div
              className={`
                max-w-[90%] rounded px-2.5 py-2 text-xs leading-relaxed
                ${msg.role === 'user'
                  ? 'bg-secondary text-white'
                  : 'bg-panel-light border border-border text-text-primary'
                }
              `}
            >
              {msg.content}
            </div>

            {msg.actions?.trades?.map((trade, i) => (
              <div
                key={i}
                className={`
                  text-xs px-2 py-1 rounded border
                  ${trade.status === 'executed'
                    ? 'border-price-up/40 text-price-up bg-price-up/10'
                    : 'border-price-down/40 text-price-down bg-price-down/10'
                  }
                `}
              >
                {trade.status === 'executed'
                  ? `${trade.side === 'buy' ? 'Bought' : 'Sold'} ${trade.quantity} ${trade.ticker} @ $${trade.price?.toFixed(2) ?? '--'}`
                  : `Failed: ${trade.ticker} - ${trade.error ?? 'Unknown error'}`
                }
              </div>
            ))}

            {msg.actions?.watchlist_changes?.map((wc, i) => (
              <div
                key={i}
                className={`
                  text-xs px-2 py-1 rounded border
                  ${wc.status === 'executed'
                    ? 'border-primary/40 text-primary bg-primary/10'
                    : 'border-text-muted/40 text-text-muted'
                  }
                `}
              >
                {wc.status === 'executed'
                  ? `${wc.action === 'add' ? 'Added' : 'Removed'} ${wc.ticker} ${wc.action === 'add' ? 'to' : 'from'} watchlist`
                  : `Watchlist ${wc.action} failed: ${wc.ticker}`
                }
              </div>
            ))}
          </div>
        ))}

        {loading && (
          <div className="flex items-start">
            <div className="bg-panel-light border border-border rounded px-3 py-2">
              <div className="flex gap-1 items-center">
                <div className="w-1.5 h-1.5 bg-primary rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <div className="w-1.5 h-1.5 bg-primary rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <div className="w-1.5 h-1.5 bg-primary rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      <div className="flex-shrink-0 border-t border-border p-2 flex gap-2">
        <input
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && !e.shiftKey && sendMessage()}
          placeholder="Ask FinAlly..."
          disabled={loading}
          className="flex-1 bg-background border border-border rounded px-2 py-1.5 text-xs text-text-primary placeholder-text-muted outline-none focus:border-primary disabled:opacity-50"
        />
        <button
          onClick={sendMessage}
          disabled={loading || !input.trim()}
          className="px-3 py-1.5 bg-secondary text-white rounded text-xs font-bold hover:opacity-90 disabled:opacity-50 transition-opacity"
        >
          Send
        </button>
      </div>
    </div>
  )
}
