export interface StrategyMeta {
  name: string
  version: string
  author: string
  description: string
  tags: string[]
  min_bars: number
  rebalance_freq: 'daily' | 'weekly' | 'monthly'
  params: ParamDef[]
  factors: FactorDef[]
}

export interface ParamDef {
  name: string
  default: number | string
  type: 'int' | 'float' | 'choice'
  min?: number
  max?: number
  choices?: string[]
  description: string
}

export interface FactorDef {
  name: string
  description: string
  category: string
}
