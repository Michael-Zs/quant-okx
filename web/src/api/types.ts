// 与后端 api/schemas.py + core/strategy/node.py 对齐的 TS 类型

export type StrategyKind = 'single' | 'multi'
export type NodeType = 'leaf' | 'signal_combiner' | 'allocation_group'

export interface ParamSchema {
  name: string
  default: number | string
  label: string
  kind: 'select' | 'slider' | 'number'
  min: number | null
  max: number | null
  step: number | null
  options: unknown[] | null
}

export interface TemplateInfo {
  name: string
  display_name: string
  description: string
  strategy_kind: StrategyKind
  kind: StrategyKind
  side_mode: string
  params: ParamSchema[]
}

export interface StrategyInstance {
  id: string
  name: string
  template_name: string
  strategy_kind: StrategyKind
  params: Record<string, number | string>
  side_mode: string
  description: string
  bar: string | null
  days: number | null
  symbols: string[]
  invert: boolean
  created_at: string
  updated_at: string
}

export interface GroupRef {
  group_id: string
  weight: number
  invert: boolean
}

export interface ChildRefSpec {
  node: NodeSpec
  weight: number
  invert: boolean
}

export interface NodeSpec {
  node_type: NodeType
  name?: string
  // leaf
  template_name?: string
  strategy_kind?: StrategyKind
  params?: Record<string, number | string>
  invert?: boolean
  // signal_combiner
  mode?: string
  // children
  children?: ChildRefSpec[]
}

export interface StrategyGroup {
  id: string
  name: string
  spec: NodeSpec
  description: string
  created_at: string
  updated_at: string
}

export interface Deployment {
  id: string
  name: string
  is_demo: boolean
  bar: string
  symbols: string[]
  check_interval_sec: number
  leverage: number
  position_ratio: number
  initial_capital: number
  groups: GroupRef[]
  alive?: boolean
  created_at: string
  updated_at: string
}

export interface BacktestMetrics {
  total_return: number
  annual_return: number
  max_drawdown: number
  sharpe: number
  sortino: number
  calmar: number
  volatility: number
  win_rate: number
  profit_factor: number | null
  n_trades: number
  final_capital: number
}

// ---- 策略实验室 ----
export interface UserStrategy {
  name: string
  filename: string
  code: string
  mtime: number
}

export interface GridSearchResult {
  [param: string]: number | string
  total_return: number
  sharpe: number
  max_drawdown: number
  sortino: number
  calmar: number
  win_rate: number
  n_trades: number
}

// ---- 多币回测明细 ----
export interface PerSymbolReport {
  symbol: string
  weight: number
  metrics: BacktestMetrics
  equity?: number[]
}
export interface SampledSeries {
  ts: string[]
  equity: number[]
  sampled?: boolean
  total_points?: number
  returned_points?: number
}
export interface MultiReport {
  metrics: BacktestMetrics
  equity: SampledSeries
  per_symbol: PerSymbolReport[]
  holdings: {
    ts: string[]
    symbols: string[]
    matrix: number[][]
    sampled?: boolean
    total_points?: number
    returned_points?: number
  }
  initial_capital: number
  response_mode?: 'full' | 'compact'
}

// ---- 设置 ----
export interface ConfigInfo {
  okx_configured: boolean
  api_host: string
  api_port: number
  api_token_set: boolean
  defaults: { leverage: number; position_ratio: number; fee: number; slippage: number }
  cache: {
    dir: string
    count: number
    size_bytes: number
    parquet_count: number
    parquet_size_bytes: number
    json_count: number
    json_size_bytes: number
  }
  strategies_dir: string
}
