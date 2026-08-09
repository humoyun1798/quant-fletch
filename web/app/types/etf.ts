// ETF 列表项 — 与 GET /api/v1/etfs 响应字段对齐 (api/src/server/routes/etfs.py:67-77)
export interface ETF {
  code: string
  name: string
  type: 'broad' | 'sector' | 'bond' | 'commodity'
  underlying: string
  inception: string | null
  expense: number | null
  latest_date: string | null
  latest_close: number | null
  change_pct: number | null
}

export interface OHLCV {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface Bar {
  dt: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export type BarPeriod = 'daily' | '1m' | '5m' | '15m' | '30m' | '60m'
