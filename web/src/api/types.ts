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
