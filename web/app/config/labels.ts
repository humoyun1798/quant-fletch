// 界面文案中文映射
//
// 为什么需要这层映射: 后端返回的指标名、参数名、选项值、动作值都是英文标识符
// (如 total_return / lookback / weekly / buy), 直接渲染到界面上就是英文文案。
// 这里统一做「标识符 → 中文」的转换, 而**不改动后端字段名**, 以免影响 API 契约。
//
// 约定: 未命中映射时原样返回标识符, 保证后端新增字段不会导致界面空白。

export const METRIC_LABELS: Record<string, string> = {
  total_return: '总收益率',
  annual_return: '年化收益率',
  annual_volatility: '年化波动率',
  sharpe_ratio: '夏普比率',
  max_drawdown: '最大回撤',
  calmar_ratio: '卡玛比率',
  win_rate: '胜率',
  benchmark_return: '基准收益',
  alpha: '超额收益',
  avg_turnover: '平均换手',
}

export function metricLabel(key: string): string {
  return METRIC_LABELS[key] ?? key
}

export const ACTION_LABELS: Record<string, string> = {
  buy: '买入',
  sell: '卖出',
  hold: '持有',
}

export function actionLabel(action: string): string {
  return ACTION_LABELS[action] ?? action
}

export const PARAM_LABELS: Record<string, string> = {
  lookback: '动量回看天数',
  top_n: '持仓数量',
  rebalance: '调仓频率',
  vol_window: '波动率窗口',
  w_momentum: '动量权重',
  w_volatility: '波动率权重',
  w_turnover: '换手率权重',
  w_correlation: '相关性权重',
  sector_weight: '行业信号权重',
  max_dd: '最大回撤止损',
  single_limit: '单标的上限',
  ma_period: '均线周期',
  max_deviation: '最大买入偏离',
  stop_factor: '止损系数',
  confirm_days: '死叉确认天数',
  cooldown_days: '冷却天数',
  min_hold_days: '最短持有天数',
  slope_lookback: '斜率回看天数',
  require_slope_up: '要求均线向上',
}

export function paramLabel(name: string): string {
  return PARAM_LABELS[name] ?? name
}

export const CHOICE_LABELS: Record<string, string> = {
  daily: '每日',
  weekly: '每周',
  monthly: '每月',
}

export function choiceLabel(value: string): string {
  return CHOICE_LABELS[value] ?? value
}

// 回测运行阶段 (BacktestTrigger)
export const STEP_LABELS: Record<string, string> = {
  preparing_features: '准备数据',
  scoring: '计算打分',
  running: '运行中',
  completed: '已完成',
  failed: '失败',
}

export function stepLabel(step: string): string {
  return STEP_LABELS[step] ?? step
}
