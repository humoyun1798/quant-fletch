import type { SignalResult } from './signal'

export interface BacktestConfig {
  strategy: string
  params: Record<string, number | string>
  start_date: string
  end_date: string
  benchmark: string
}

export interface BacktestResult {
  run_id: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  metrics: Metrics | null
  equity_curve: EquityPoint[]
  signals: SignalResult[]
}

export interface Metrics {
  annual_return: number
  annual_volatility: number
  sharpe_ratio: number
  max_drawdown: number
  calmar_ratio: number
  win_rate: number
  total_return: number
  benchmark_return: number
  alpha: number
  avg_turnover: number
}

export interface EquityPoint {
  date: string
  equity: number
  benchmark: number
}
