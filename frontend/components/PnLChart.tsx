'use client'

import { useEffect, useRef } from 'react'
import type { HistoryPoint } from '@/types'

interface PnLChartProps {
  history: HistoryPoint[]
}

type LWC = typeof import('lightweight-charts')

export default function PnLChart({ history }: PnLChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const chartRef = useRef<any>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const seriesRef = useRef<any>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const baselineRef = useRef<any>(null)

  useEffect(() => {
    if (!containerRef.current) return

    import('lightweight-charts').then((lwc: LWC) => {
      if (!containerRef.current || chartRef.current) return

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
        rightPriceScale: {
          borderColor: '#2a2a4a',
        },
        timeScale: {
          borderColor: '#2a2a4a',
          timeVisible: true,
          secondsVisible: false,
        },
        handleScroll: false,
        handleScale: false,
      })

      seriesRef.current = chart.addLineSeries({
        color: '#209dd7',
        lineWidth: 2,
        priceLineVisible: false,
      })

      baselineRef.current = chart.addLineSeries({
        color: '#ecad0a',
        lineWidth: 1,
        lineStyle: 2,
        priceLineVisible: false,
      })

      chartRef.current = chart

      const ro = new ResizeObserver(() => {
        if (containerRef.current && chartRef.current) {
          chartRef.current.applyOptions({
            width: containerRef.current.clientWidth,
            height: containerRef.current.clientHeight,
          })
        }
      })
      ro.observe(containerRef.current)
    })

    return () => {
      if (chartRef.current) {
        chartRef.current.remove()
        chartRef.current = null
        seriesRef.current = null
        baselineRef.current = null
      }
    }
  }, [])

  useEffect(() => {
    if (!seriesRef.current || !baselineRef.current || !history.length) return

    const raw = history.map(h => ({
      time: Math.floor(new Date(h.recorded_at).getTime() / 1000),
      value: h.total_value,
    }))

    // Deduplicate by time, keep last
    const seen = new Map<number, { time: number; value: number }>()
    for (const d of raw) seen.set(d.time, d)
    const data = Array.from(seen.values()).sort((a, b) => a.time - b.time)

    seriesRef.current.setData(data)

    if (data.length >= 2) {
      baselineRef.current.setData([
        { time: data[0].time, value: 10000 },
        { time: data[data.length - 1].time, value: 10000 },
      ])
    }

    chartRef.current?.timeScale().fitContent()
  }, [history])

  return (
    <div className="flex flex-col h-full bg-panel">
      <div className="px-3 py-1.5 border-b border-border flex-shrink-0">
        <span className="text-text-muted text-xs uppercase tracking-wider font-bold">P&amp;L History</span>
      </div>
      <div ref={containerRef} className="flex-1 min-h-0" />
    </div>
  )
}
