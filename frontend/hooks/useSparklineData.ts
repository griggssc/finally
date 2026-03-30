'use client'

import { useRef, useEffect } from 'react'
import type { PriceUpdate } from '@/types'

const MAX_POINTS = 300

export function useSparklineData(
  prices: Map<string, PriceUpdate>
): Map<string, number[]> {
  const historyRef = useRef<Map<string, number[]>>(new Map())
  const prevPricesRef = useRef<Map<string, number>>(new Map())

  for (const [ticker, update] of prices.entries()) {
    const prevPrice = prevPricesRef.current.get(ticker)
    if (prevPrice === update.price) continue

    prevPricesRef.current.set(ticker, update.price)

    const arr = historyRef.current.get(ticker) ?? []
    arr.push(update.price)
    if (arr.length > MAX_POINTS) arr.shift()
    historyRef.current.set(ticker, arr)
  }

  return historyRef.current
}
