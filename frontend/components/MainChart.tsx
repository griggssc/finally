'use client'

import { useEffect, useRef } from 'react'
import type { PriceUpdate } from '@/types'

interface MainChartProps {
  ticker: string
  prices: Map<string, PriceUpdate>
}

type LWC = typeof import('lightweight-charts')

export default function MainChart({ ticker, prices }: MainChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const chartRef = useRef<any>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const seriesRef = useRef<any>(null)
  const dataRef = useRef<{ time: number; value: number }[]>([])
  const prevTickerRef = useRef<string>('')

  useEffect(() => {
    if (!containerRef.current) return

    let cleanupResize: (() => void) | undefined

    import('lightweight-charts').then((lwc: LWC) => {
      if (!containerRef.current) return

      const chart = lwc.createChart(containerRef.current, {
        width: containerRef.current.clientWidth,
        height: containerRef.current.clientHeight,
        layout: {
          background: { color: '#1a1a2e' },
          textColor: '#8b8b9e',
        },
        grid: {
          vertLines: { color: '#2a2a4a' },
          horzLines: { color: '#2a2a4a' },
        },
        crosshair: {
          mode: lwc.CrosshairMode.Normal,
        },
        rightPriceScale: {
          borderColor: '#2a2a4a',
        },
        timeScale: {
          borderColor: '#2a2a4a',
          timeVisible: true,
          secondsVisible: false,
        },
      })

      const series = chart.addAreaSeries({
        lineColor: '#209dd7',
        topColor: 'rgba(32, 157, 215, 0.3)',
        bottomColor: 'rgba(32, 157, 215, 0.0)',
        lineWidth: 2,
        priceLineVisible: true,
        priceLineColor: '#ecad0a',
        priceLineWidth: 1,
      })

      chartRef.current = chart
      seriesRef.current = series

      const ro = new ResizeObserver(() => {
        if (containerRef.current && chartRef.current) {
          chartRef.current.applyOptions({
            width: containerRef.current.clientWidth,
            height: containerRef.current.clientHeight,
          })
        }
      })
      ro.observe(containerRef.current)
      cleanupResize = () => ro.disconnect()
    })

    return () => {
      cleanupResize?.()
      if (chartRef.current) {
        chartRef.current.remove()
        chartRef.current = null
        seriesRef.current = null
      }
    }
  }, [])

  // Reset data when ticker changes
  useEffect(() => {
    if (prevTickerRef.current !== ticker) {
      prevTickerRef.current = ticker
      dataRef.current = []
      if (seriesRef.current) {
        seriesRef.current.setData([])
      }
    }
  }, [ticker])

  // Update chart on new price for selected ticker
  useEffect(() => {
    const update = prices.get(ticker)
    if (!update || !seriesRef.current) return

    const time = Math.floor(new Date(update.timestamp).getTime() / 1000)
    const data = dataRef.current

    if (data.length > 0 && data[data.length - 1].time === time) {
      data[data.length - 1] = { time, value: update.price }
    } else {
      data.push({ time, value: update.price })
    }

    seriesRef.current.update({ time, value: update.price })
  }, [ticker, prices])

  const currentPrice = prices.get(ticker)

  return (
    <div className="flex flex-col h-full bg-panel">
      <div className="px-3 py-1.5 border-b border-border flex items-center gap-3 flex-shrink-0">
        <span className="text-accent font-bold text-sm">{ticker}</span>
        {currentPrice && (
          <>
            <span className="text-text-primary font-mono text-sm">${currentPrice.price.toFixed(2)}</span>
            <span className={`text-xs font-mono ${currentPrice.change_percent >= 0 ? 'text-price-up' : 'text-price-down'}`}>
              {currentPrice.change_percent >= 0 ? '+' : ''}{currentPrice.change_percent.toFixed(2)}%
            </span>
          </>
        )}
        <span className="text-text-muted text-xs ml-auto">Today</span>
      </div>
      <div ref={containerRef} className="flex-1 min-h-0" />
    </div>
  )
}
