import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { MetricCard } from './ui'
import { fmt, pct } from '../lib/utils'
import type { BacktestMetrics, BenchmarkMetrics } from '../api/types'

export function EquityChart({ equity, benchmark }: {
  equity: { ts: string[]; equity: number[] } | null
  benchmark?: { ts: string[]; equity: number[] } | null
}) {
  if (!equity || !equity.equity?.length) {
    return <div className="text-dim text-sm py-16 text-center">无权益数据</div>
  }
  // 把策略与基准各自归一化到首点=1，使两条曲线可比（两者初始资金/撞动不同，
  // 不归一化会变成「斜率不同的两条线」看不出差异）。视觉差 = 累计 alpha。
  const rebase = (xs: number[]) => {
    const b0 = xs[0]
    return b0 > 0 ? xs.map((v) => v / b0) : xs
  }
  const eqNorm = rebase(equity.equity)
  const hasBench = !!benchmark && !!benchmark.equity?.length
  const bnNorm = hasBench ? rebase(benchmark!.equity) : null
  const data = eqNorm.map((v, i) => ({ i, v, b: bnNorm ? bnNorm[i] ?? null : null }))
  const last = eqNorm[eqNorm.length - 1]
  const first = eqNorm[0]
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
                 formatter={(v: number, n: string) =>
                   [fmt(v), n === 'v' ? '策略' : '基准 buy & hold']} />
        <Line type="monotone" dataKey="v" stroke={color} strokeWidth={2} dot={false} fill="url(#eq)" />
        {hasBench && (
          <Line type="monotone" dataKey="b" stroke="#94a3b8" strokeWidth={1.5}
                strokeDasharray="4 4" dot={false} isAnimationActive={false} />
        )}
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
    <div className="space-y-4">
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
      {m.benchmark && <BenchmarkGrid b={m.benchmark} />}
    </div>
  )
}

/** 基准对比指标：判断策略是真有 alpha 还是只是跟大盘涨。
 *  - beta：相对现货市场的杠杆（纯满仓做多 → ≈ position_ratio*leverage）
 *  - alpha：年化超额收益，剥除 beta 后真正的 edge（>0 才说明策略有价值）
 *  - 信息比率：相对大盘的超额收益 / 跟踪误差，比夏普更能反映独立优势
 *  - 相关性：与基准走势的相关系数（高 + 低 alpha = 没有独立价值） */
export function BenchmarkGrid({ b }: { b: BenchmarkMetrics }) {
  const tone = (v: number): 'up' | 'down' | undefined => (v > 0 ? 'up' : v < 0 ? 'down' : undefined)
  const alphaHint = b.alpha >= 0
    ? '剥除 beta 后的真实超额收益（年化）'
    : '低于基准表现 · alpha≈0 且高相关 = 只是在跟大盘'
  const betaHint = b.beta > 0.7 ? '高度跟随大盘' : b.beta < 0.2 ? '基本对冲掉了大盘方向' : '部分跟随大盘'
  return (
    <div className="rounded border border-line bg-card/40 p-3">
      <div className="text-[0.7rem] uppercase tracking-wider text-dim mb-2">基准对比 · 相对现货币 buy &amp; hold</div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MetricCard label="Alpha (年化)" value={pct(b.alpha)} sub={alphaHint} tone={tone(b.alpha)} />
        <MetricCard label="Beta" value={fmt(b.beta)} sub={betaHint} />
        <MetricCard label="信息比率" value={fmt(b.information_ratio)} tone={tone(b.information_ratio)} />
        <MetricCard label="与基准相关" value={fmt(b.correlation)} sub={'超额收益 ' + pct(b.excess_return)} />
      </div>
    </div>
  )
}
