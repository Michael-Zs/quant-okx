import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { MetricCard } from './ui'
import { fmt, pct } from '../lib/utils'
import type { BacktestMetrics } from '../api/types'

export function EquityChart({ equity }: { equity: { ts: string[]; equity: number[] } | null }) {
  if (!equity || !equity.equity?.length) {
    return <div className="text-dim text-sm py-16 text-center">无权益数据</div>
  }
  const data = equity.equity.map((v, i) => ({ i, v }))
  const last = equity.equity[equity.equity.length - 1]
  const first = equity.equity[0]
  const color = last >= first ? '#34d399' : '#f87171'
  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id="eq" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.3} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <XAxis dataKey="i" stroke="#8b97a7" tick={{ fontSize: 11 }} tickLine={false}
               axisLine={{ stroke: 'rgba(255,255,255,0.08)' }} />
        <YAxis stroke="#8b97a7" tick={{ fontSize: 11 }} tickLine={false} axisLine={false}
               width={58} domain={['auto', 'auto']} />
        <Tooltip contentStyle={{ background: '#0e1320', border: '1px solid rgba(255,255,255,0.09)',
                                 borderRadius: 8, fontSize: 12 }}
                 labelStyle={{ color: '#8b97a7' }}
                 formatter={(v: number) => [fmt(v), '权益']} />
        <Line type="monotone" dataKey="v" stroke={color} strokeWidth={2} dot={false}
              fill="url(#eq)" />
      </LineChart>
    </ResponsiveContainer>
  )
}

export function MetricsGrid({ m }: { m: BacktestMetrics | null }) {
  if (!m) {
    return <div className="text-dim text-sm py-8 text-center">调整参数查看回测指标</div>
  }
  const tone = (v: number): 'up' | 'down' | undefined => (v > 0 ? 'up' : v < 0 ? 'down' : undefined)
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      <MetricCard label="总收益" value={pct(m.total_return)} tone={tone(m.total_return)} />
      <MetricCard label="年化" value={pct(m.annual_return)} tone={tone(m.annual_return)} />
      <MetricCard label="最大回撤" value={pct(m.max_drawdown)} tone="down" />
      <MetricCard label="夏普" value={fmt(m.sharpe)} />
      <MetricCard label="索提诺" value={fmt(m.sortino)} />
      <MetricCard label="卡尔玛" value={fmt(m.calmar)} />
      <MetricCard label="胜率" value={pct(m.win_rate)} />
      <MetricCard label="交易次数" value={m.n_trades} />
    </div>
  )
}
