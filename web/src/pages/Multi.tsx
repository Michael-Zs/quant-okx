import { useEffect, useState } from 'react'
import { Activity, Play, RefreshCcw, Save, Bot } from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { api } from '../api/client'
import type { TemplateInfo, MultiReport, ParamSchema } from '../api/types'
import { Card, CardHeader, Button, Input, Field, Slider, Select, Badge, Toggle } from '../components/ui'
import { MultiSymbolPicker } from '../components/SymbolPicker'
import { SpecModal } from '../components/SpecModal'
import { useStore } from '../store/useStore'
import { pct, fmt } from '../lib/utils'

const DEFAULT_UNIVERSE = ['BTC-USDT-SWAP', 'ETH-USDT-SWAP', 'SOL-USDT-SWAP']
const STRAT_COLORS = ['#22d3ee', '#a78bfa', '#34d399', '#f87171', '#fbbf24', '#60a5fa', '#f472b6', '#94a3b8']

export default function Multi() {
  const [templates, setTemplates] = useState<TemplateInfo[]>([])
  const [instruments, setInstruments] = useState<string[]>([])
  const [sel, setSel] = useState('')
  const [universe, setUniverse] = useState<string[]>(DEFAULT_UNIVERSE)
  const [bar, setBar] = useState('1H')
  const [days, setDays] = useState(180)
  const [params, setParams] = useState<Record<string, number | string>>({})
  const [alloc, setAlloc] = useState<Record<string, number>>({})
  const [invert, setInvert] = useState(false)
  const [loading, setLoading] = useState(false)
  const [report, setReport] = useState<MultiReport | null>(null)
  const [err, setErr] = useState('')
  const [saveName, setSaveName] = useState('')
  const [msg, setMsg] = useState('')
  const [specOpen, setSpecOpen] = useState(false)
  const { refreshStrategies } = useStore()

  useEffect(() => {
    api.templates().then((r) => {
      setTemplates(r.templates)
      const m = r.templates.find((t) => t.strategy_kind === 'multi')
      const first = m || r.templates[0]
      if (first) setSel(first.name)
    })
    api.instruments().then((r) => setInstruments(r.instruments)).catch(() => {})
  }, [])

  const tpl = templates.find((t) => t.name === sel)
  useEffect(() => {
    if (tpl) setParams(Object.fromEntries(tpl.params.map((p) => [p.name, p.default])))
  }, [sel, tpl])
  // universe 变化时重置分配为等权
  useEffect(() => {
    setAlloc(Object.fromEntries(universe.map((s) => [s, 1])))
  }, [universe.join('|')])

  async function run() {
    setLoading(true); setErr('')
    try {
      const r = await api.multiBacktest({
        node_spec: { node_type: 'leaf', name: tpl!.name, template_name: tpl!.name, strategy_kind: tpl!.strategy_kind, params, invert: false },
        symbols: universe, bar, days, allocation: alloc, invert,
      })
      setReport(r)
    } catch (e) { setErr((e as Error).message); setReport(null) }
    finally { setLoading(false) }
  }

  async function save() {
    if (!tpl || !saveName) return
    try {
      await api.createStrategy({
        name: saveName, template_name: tpl.name,
        strategy_kind: tpl.strategy_kind, params,
        bar, days, symbols: universe, invert,
      })
      await refreshStrategies()
      setMsg(`✓ 已保存${isMulti ? '多币' : '批量'}策略「${saveName}」`)
      setSaveName('')
    } catch (e) { setMsg((e as Error).message) }
  }

  const isMulti = tpl?.strategy_kind === 'multi'
  const eqData = report?.equity
  const overlayData = (() => {
    if (!report) return []
    const n = report.equity.ts.length
    return Array.from({ length: n }, (_, i) => {
      const row: Record<string, number | string> = { i }
      row['组合'] = report.equity.equity[i]
      for (const p of report.per_symbol) row[p.symbol.split('-')[0]] = p.equity[i]
      return row
    })
  })()

  return (
    <div className="flex flex-col h-full">
      <div className="px-6 pt-5 pb-3 border-b border-line flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight flex items-center gap-2">
            <Activity size={20} className="text-accent" /> 多币策略
          </h1>
          <p className="text-xs text-dim mt-0.5">跨币种择优（动量轮动 / 相对强弱）+ 单币策略多币批量运行 · 资金槽模型。</p>
        </div>
        <button onClick={() => setSpecOpen(true)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium border border-accent/30 text-accent hover:bg-accent/10 transition-colors shrink-0">
          <Bot size={14} /> AI 规范（多币）
        </button>
      </div>

      <div className="flex flex-1 min-h-0">
        {/* 左：配置 */}
        <div className="w-80 shrink-0 border-r border-line p-4 overflow-auto">
          <Field label="策略" hint={isMulti ? '跨币策略：同时看多币择优' : '单币策略：在各币独立批量运行'}>
            <select value={sel} onChange={(e) => setSel(e.target.value)}
              className="w-full px-3 py-2 rounded-sm bg-black/30 border border-line text-sm text-text outline-none focus:border-accent">
              {templates.map((t) => <option key={t.name} value={t.name} className="bg-bg2">{t.display_name}{t.strategy_kind === 'multi' ? ' · 跨币' : ''}</option>)}
            </select>
          </Field>
          <div className="text-xs text-dim mt-1.5">{tpl?.description}</div>

          <div className="mt-3">
            <Field label="币种池 universe（≥2）">
              <MultiSymbolPicker value={universe} onChange={setUniverse} instruments={instruments} min={2} />
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-2 mt-3">
            <Field label="周期">
              <Select value={bar} onChange={setBar} options={['1H', '4H', '1D'].map((b) => ({ value: b, label: b }))} className="w-full" />
            </Field>
            <Field label="天数"><Input type="number" value={days} onChange={(e) => setDays(+e.target.value)} className="w-full" /></Field>
          </div>

          <div className="h-px bg-line my-4" />
          <div className="text-xs text-dim mb-2">策略参数</div>
          <div className="space-y-3">
            {tpl?.params.map((p) => (
              <ParamControl key={p.name} p={p} value={params[p.name]}
                onChange={(v) => setParams((s) => ({ ...s, [p.name]: v }))} />
            ))}
          </div>

          <div className="h-px bg-line my-4" />
          <div className="text-xs text-dim mb-2">资金分配（各币种资金槽占比）</div>
          <div className="space-y-2.5">
            {universe.map((s) => (
              <div key={s}>
                <div className="flex justify-between text-xs mb-0.5"><span>{s.split('-')[0]}</span><span className="text-dim">{alloc[s]?.toFixed(2) ?? '1.00'}</span></div>
                <Slider value={alloc[s] ?? 1} min={0} max={2} step={0.1} onChange={(v) => setAlloc((a) => ({ ...a, [s]: v }))} />
              </div>
            ))}
          </div>

          <div className="h-px bg-line my-4" />
          <label className="flex items-center justify-between cursor-pointer mb-3">
            <span className="text-xs text-dim">反转信号（1↔-1）</span>
            <Toggle checked={invert} onChange={setInvert} />
          </label>
          <Button variant="primary" className="w-full" onClick={run} disabled={loading || universe.length < 2}>
            <Play size={15} className="inline mr-1.5" />{loading ? '回测中…' : '组合回测'}
          </Button>
          {err && <div className="text-xs text-down mt-2 break-all">{err}</div>}

          <div className="h-px bg-line my-4" />
          <div className="text-xs text-dim mb-2">保存为策略实例</div>
          <Input value={saveName} onChange={(e) => setSaveName(e.target.value)} placeholder="命名（如：动量轮动_v1）…" className="w-full mb-2" />
          <Button variant="secondary" className="w-full" onClick={save} disabled={!saveName || !tpl}>
            <Save size={15} className="inline mr-1.5" />保存策略
          </Button>
          {msg && <div className="text-xs text-accent mt-2 break-all">{msg}</div>}
        </div>

        {/* 右：结果 */}
        <div className="flex-1 overflow-auto p-4 space-y-4">
          {!report ? (
            <div className="text-dim text-sm py-16 text-center">选好币种池与策略，点「组合回测」查看结果</div>
          ) : (
            <>
              {/* 指标 */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <MetricBox label="组合总收益" v={pct(report.metrics.total_return)} tone={report.metrics.total_return >= 0 ? 'up' : 'down'} />
                <MetricBox label="年化" v={pct(report.metrics.annual_return)} />
                <MetricBox label="最大回撤" v={pct(report.metrics.max_drawdown)} tone="down" />
                <MetricBox label="夏普" v={fmt(report.metrics.sharpe)} />
              </div>

              {/* 权益叠加 */}
              <Card>
                <CardHeader title="组合权益 vs 各币种权益" subtitle={`${universe.length} 币种 · ${bar} · ${days}天${invert ? ' · 反向' : ''}`}
                  action={<Badge color="accent-2">资金槽合成</Badge>} />
                <div className="px-3 pb-3">
                  <ResponsiveContainer width="100%" height={300}>
                    <LineChart data={overlayData} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
                      <XAxis dataKey="i" stroke="#8b97a7" tick={{ fontSize: 11 }} tickLine={false} axisLine={{ stroke: 'rgba(255,255,255,0.08)' }} />
                      <YAxis stroke="#8b97a7" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} width={58} domain={['auto', 'auto']} />
                      <Tooltip contentStyle={{ background: '#0e1320', border: '1px solid rgba(255,255,255,0.09)', borderRadius: 8, fontSize: 12 }} labelStyle={{ color: '#8b97a7' }} formatter={(v: number) => fmt(v)} />
                      <Legend wrapperStyle={{ fontSize: 11 }} />
                      {['组合', ...report.per_symbol.map((p) => p.symbol.split('-')[0])].map((k, i) => (
                        <Line key={k} type="monotone" dataKey={k} stroke={i === 0 ? '#4dd0e1' : STRAT_COLORS[(i - 1) % STRAT_COLORS.length]}
                              strokeWidth={i === 0 ? 2.5 : 1} dot={false} strokeDasharray={i === 0 ? undefined : '4 3'} />
                      ))}
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </Card>

              {/* 持仓热力图 */}
              <Card>
                <CardHeader title="持仓时间线（绿=持仓 / 深色=空仓）" subtitle="各币种 signal 随时间的分布" />
                <div className="px-4 pb-4">
                  <HoldingsHeatmap report={report} />
                </div>
              </Card>

              {/* 各币种贡献 */}
              <Card>
                <CardHeader title="各币种贡献明细" />
                <div className="overflow-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-dim border-b border-line">
                        {['币种', '资金占比', '总收益', '最大回撤', '夏普', '胜率', '交易次数'].map((h, i) => (
                          <th key={h} className={`${i < 2 ? 'text-left' : 'text-right'} px-3 py-2 font-medium`}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {report.per_symbol.map((p) => (
                        <tr key={p.symbol} className="border-b border-line/40 hover:bg-card">
                          <td className="px-3 py-1.5 font-medium">{p.symbol.split('-')[0]}</td>
                          <td className="px-3 py-1.5 text-dim">{pct(p.weight)}</td>
                          <td className={`px-3 py-1.5 text-right tnum ${p.metrics.total_return >= 0 ? 'text-up' : 'text-down'}`}>{pct(p.metrics.total_return)}</td>
                          <td className="px-3 py-1.5 text-right tnum text-down">{pct(p.metrics.max_drawdown)}</td>
                          <td className="px-3 py-1.5 text-right tnum">{fmt(p.metrics.sharpe)}</td>
                          <td className="px-3 py-1.5 text-right tnum">{pct(p.metrics.win_rate)}</td>
                          <td className="px-3 py-1.5 text-right tnum text-dim">{p.metrics.n_trades}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            </>
          )}
        </div>
      </div>
      {specOpen && <SpecModal kind="multi" onClose={() => setSpecOpen(false)} />}
    </div>
  )
}

function MetricBox({ label, v, tone }: { label: string; v: string; tone?: 'up' | 'down' }) {
  return (
    <div className="rounded border border-line bg-card p-3.5">
      <div className="text-[0.7rem] uppercase tracking-wider text-dim">{label}</div>
      <div className={`text-xl font-semibold tnum mt-1 ${tone === 'up' ? 'text-up' : tone === 'down' ? 'text-down' : ''}`}>{v}</div>
    </div>
  )
}

/** 持仓热力图：横轴=时间采样，纵轴=币种，单元格用颜色深浅表示持仓。 */
function HoldingsHeatmap({ report }: { report: MultiReport }) {
  const { symbols, matrix, ts } = report.holdings
  const total = ts.length
  // 把 total 根 K线下采样到固定列数（性能 + 可读性）
  const COLS = Math.min(120, total)
  const step = Math.max(1, Math.floor(total / COLS))
  const cols: number[] = []
  for (let i = 0; i < total; i += step) cols.push(i)
  const realCols = cols.length

  return (
    <div className="overflow-auto">
      <div className="text-[0.7rem] text-dim mb-2">横轴：时间（左→右），{total} 根 K 线下采样到 {realCols} 列</div>
      <div className="space-y-1">
        {symbols.map((sym, si) => (
          <div key={sym} className="flex items-center gap-2">
            <div className="w-12 text-[0.7rem] text-dim shrink-0">{sym.split('-')[0]}</div>
            <div className="flex gap-px flex-1">
              {cols.map((t, ci) => {
                // 该时间窗内是否持仓（取窗口内任一根为持仓即亮）
                let held = 0
                for (let k = t; k < Math.min(t + step, total); k++) if (matrix[si][k] !== 0) { held = matrix[si][k]; break }
                const bg = held === 1 ? '#00e676' : held === -1 ? '#f87171' : 'rgba(255,255,255,0.04)'
                return <div key={ci} title={`${sym} @ ${ts[t]}`} style={{ background: bg }} className="h-3.5 flex-1 rounded-[1px]" />
              })}
            </div>
          </div>
        ))}
      </div>
      <div className="flex items-center gap-4 mt-3 text-[0.7rem] text-dim">
        <span className="flex items-center gap-1"><span className="inline-block w-3 h-3 rounded-sm" style={{ background: '#00e676' }} /> 做多</span>
        <span className="flex items-center gap-1"><span className="inline-block w-3 h-3 rounded-sm" style={{ background: '#f87171' }} /> 做空</span>
        <span className="flex items-center gap-1"><span className="inline-block w-3 h-3 rounded-sm" style={{ background: 'rgba(255,255,255,0.04)' }} /> 空仓</span>
      </div>
    </div>
  )
}

function ParamControl({ p, value, onChange }: { p: ParamSchema; value: number | string; onChange: (v: number | string) => void }) {
  if (p.kind === 'select' && p.options) {
    return (
      <Field label={p.label || p.name}>
        <Select value={String(value)} onChange={onChange} className="w-full" options={p.options.map((o) => ({ value: String(o), label: String(o) }))} />
      </Field>
    )
  }
  if (p.kind === 'slider') {
    return (
      <Field label={`${p.label || p.name}：${value}`}>
        <Slider value={Number(value)} min={p.min ?? 0} max={p.max ?? 100} step={p.step ?? 1} onChange={onChange} />
      </Field>
    )
  }
  return (
    <Field label={p.label || p.name}>
      <Input type="number" value={Number(value)} onChange={(e) => onChange(+e.target.value)} className="w-full" />
    </Field>
  )
}
