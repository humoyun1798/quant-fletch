export interface Signal {
  code: string
  action: 'buy' | 'sell' | 'hold'
  target_weight: number
  confidence: number
  reason: string
}

export interface SignalResult {
  date: string
  signals: Signal[]
  total_positions: number
  turnover: number
  cash_ratio: number
  summary: string
}
