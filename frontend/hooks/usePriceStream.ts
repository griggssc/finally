'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import type { PriceUpdate, ConnectionStatus } from '@/types'

export interface PriceStreamResult {
  prices: Map<string, PriceUpdate>
  status: ConnectionStatus
}

export function usePriceStream(): PriceStreamResult {
  const [prices, setPrices] = useState<Map<string, PriceUpdate>>(new Map())
  const [status, setStatus] = useState<ConnectionStatus>('disconnected')
  const esRef = useRef<EventSource | null>(null)
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const retryCount = useRef(0)

  const connect = useCallback(() => {
    if (esRef.current) {
      esRef.current.close()
    }

    setStatus('reconnecting')
    const es = new EventSource('/api/stream/prices')
    esRef.current = es

    es.onopen = () => {
      setStatus('connected')
      retryCount.current = 0
    }

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as Record<string, PriceUpdate>
        setPrices(prev => {
          const next = new Map(prev)
          for (const [ticker, update] of Object.entries(data)) {
            next.set(ticker, update)
          }
          return next
        })
      } catch {
        // ignore parse errors
      }
    }

    es.onerror = () => {
      setStatus('reconnecting')
      es.close()
      esRef.current = null

      const delay = Math.min(1000 * Math.pow(2, retryCount.current), 30000)
      retryCount.current++
      retryRef.current = setTimeout(connect, delay)
    }
  }, [])

  useEffect(() => {
    connect()
    return () => {
      if (esRef.current) {
        esRef.current.close()
        esRef.current = null
      }
      if (retryRef.current) {
        clearTimeout(retryRef.current)
      }
    }
  }, [connect])

  return { prices, status }
}
