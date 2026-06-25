import { useEffect, useRef, useState } from 'react'
import { Save, Bot } from 'lucide-react'
import { api, openBacktestWS } from '../api/client'
import type { TemplateInfo, BacktestMetrics, NodeSpec, ParamSchema } from '../api/types'
import { Card, CardHeader, Button, Slider, Select, Input, Field } from '../components/ui'
import { EquityChart, MetricsGrid } from '../components/charts'
import { SymbolPicker } from '../components/SymbolPicker'
import { SpecModal } from '../components/SpecModal'
import { useStore } from '../store/useStore'

const BARS = ['1H', '4H', '1D']

export default function Explore() {
  const [templates, setTemplates] = useState<TemplateInfo[]>([])
  const [sel, setSel] = useState('')
  const [params, setParams] = useState<Record<string, number | string>>({})
  const [symbol, setSymbol] = useState('BTC-USDT-SWAP')
  const [instruments, setInstruments] = useState<string[]>([
    'BTC-USDT-SWAP', 'ETH-USDT-SWAP', 'SOL-USDT-SWAP', 'DOGE-USDT-SWAP', 'XRP-USDT-SWAP',
  ])
  const [bar, setBar] = useState('1H')
  const [days, setDays] = useState(180)
  const [invert, setInvert] = useState(false)
  const [metrics, setMetrics] = useState<BacktestMetrics | null>(null)
  const [equity, setEquity] = useState<{ ts: string[]; equity: number[] } | null>(null)
  const [benchmark, setBenchmark] = useState<{ ts: string[]; equity: number[] } | null>(null)
  const [saveName, setSaveName] = useState('')
  const [msg, setMsg] = useState('')
  const [specOpen, setSpecOpen] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const { refreshStrategies } = useStore()

  useEffect(() => {
    api.templates().then((r) => {
      setTemplates(r.templates)
      const first = r.templates.find((t) => t.strategy_kind === 'single')
      if (first) setSel(first.name)
    })
    api.instruments().then((r) => setInstruments(r.instruments)).catch(() => {})
  }, [])

  const tpl = templates.find((t) => t.name === sel)
  useEffect(() => {
    if (tpl) setParams(Object.fromEntries(tpl.params.map((p) => [p.name, p.default])))
  }, [sel, tpl])

  // WS 实时预览连接
  useEffect(() => {
    const ws = openBacktestWS((d) => {
      if (d.metrics) {
        setMetrics(d.metrics as BacktestMetrics)
        setEquity(d.equity as { ts: string[]; equity: number[] })
        setBenchmark((d.benchmark as { ts: string[]; equity: number[] }) ?? null)
      } else if (d.error) setMsg(String(d.error))
    })
    wsRef.current = ws
    return () => ws.close()
  }, [])

  // 参数/品种/invert 变化时发回测（debounce 300ms）
  useEffect(() => {
    const ws = wsRef.current
    if (!tpl || !ws || ws.readyState !== WebSocket.OPEN) return
    const t = setTimeout(() => {
      const spec: NodeSpec = {
        node_type: 'leaf', name: tpl.name, template_name: tpl.name,
        strategy_kind: tpl.strategy_kind, params, invert,
      }
      ws.send(JSON.stringify({ node_spec: spec, symbols: [symbol], bar, days, initial_capital: 10000 }))
    }, 300)
    return () => clearTimeout(t)
  }, [tpl, params, symbol, bar, days, invert])

  async function save() {
    if (!tpl || !saveName) return
    try {
      await api.createStrategy({
        name: saveName, template_name: tpl.name,
        strategy_kind: tpl.strategy_kind, params,
        bar, days,
        symbols: [symbol],
        invert,
      })
      await refreshStrategies()
      setMsg(`✓ 已保存单策略「${saveName}」`)
      setSaveName('')
    } catch (e) {
      setMsg((e as Error).message)
    }
  }

  const visible = templates.filter((t) => t.strategy_kind === 'single')

  return (
    <div className="flex h-full">
      {/* 左：模板库 */}
      <div className="w-72 shrink-0 border-r border-line p-4 overflow-auto">
        <button onClick={() => setSpecOpen(true)}
          className="w-full mb-3 flex items-center justify-center gap-1.5 py-1.5 rounded text-xs font-medium border border-accent/30 text-accent hover:bg-accent/10 transition-colors">
          <Bot size={14} /> AI 策略开发规范（单币）
        </button>
        <div className="space-y-1">
          {visible.map((t) => (
            <button key={t.name} onClick={() => setSel(t.name)}
              className={`w-full text-left px-3 py-2.5 rounded transition-colors ${sel === t.name ? 'bg-card-strong border border-accent/30' : 'hover:bg-card border border-transparent'}`}>
              <div className="text-sm font-medium">{t.display_name}</div>
              <div className="text-xs text-dim mt-0.5 line-clamp-2">{t.description}</div>
            </button>
          ))}
        </div>
      </div>

      {/* 中：参数 */}
      <div className="w-72 shrink-0 border-r border-line p-4 overflow-auto">
        {tpl ? (
          <>
            <div className="text-base font-semibold">{tpl.display_name}</div>
            <div className="text-xs text-dim mb-4">{tpl.description}</div>
            <Field label="品种（合约）">
              <SymbolPicker value={symbol} onChange={setSymbol} instruments={instruments} />
            </Field>
            <div className="grid grid-cols-2 gap-2 mt-3">
              <Field label="周期">
                <Select value={bar} onChange={setBar} options={BARS.map((b) => ({ value: b, label: b }))} className="w-full" />
              </Field>
              <Field label="回测天数">
                <Input type="number" value={days} onChange={(e) => setDays(+e.target.value)} className="w-full" />
              </Field>
            </div>
            <label className="flex items-center justify-between mt-4 cursor-pointer">
              <span className="text-xs text-dim">反向（做空基准）</span>
              <input type="checkbox" checked={invert} onChange={(e) => setInvert(e.target.checked)} className="accent-accent" />
            </label>
            <div className="h-px bg-line my-4" />
            <div className="text-xs text-dim mb-3">参数</div>
            <div className="space-y-4">
              {tpl.params.map((p) => (
                <ParamControl key={p.name} p={p} value={params[p.name]}
                              onChange={(v) => setParams((s) => ({ ...s, [p.name]: v }))} />
              ))}
            </div>
            <div className="h-px bg-line my-4" />
            <Field label="保存为单策略实例">
              <Input value={saveName} onChange={(e) => setSaveName(e.target.value)} placeholder="给这个参数组合命名…" className="w-full" />
            </Field>
            <Button variant="primary" className="w-full mt-2" onClick={save} disabled={!saveName}>
              <Save size={15} className="inline mr-1.5" />保存单策略
            </Button>
            {msg && <div className="text-xs text-accent mt-2 break-all">{msg}</div>}
          </>
        ) : (
          <div className="text-dim text-sm">选择左侧模板</div>
        )}
      </div>

      {/* 右：实时回测预览 */}
      <div className="flex-1 p-4 overflow-auto">
        <Card>
          <CardHeader title="权益曲线"
            subtitle={tpl ? `${tpl.display_name} · ${symbol} ${bar} · ${days}天${invert ? ' · 反向' : ''}` : ''} />
          <div className="px-4 pb-4"><EquityChart equity={equity} benchmark={benchmark} /></div>
        </Card>
        <div className="mt-4"><MetricsGrid m={metrics} /></div>
      </div>

      {specOpen && <SpecModal kind="single" onClose={() => setSpecOpen(false)} />}
    </div>
  )
}

function ParamControl({ p, value, onChange }: { p: ParamSchema; value: number | string; onChange: (v: number | string) => void }) {
  if (p.kind === 'select' && p.options) {
    return (
      <Field label={p.label || p.name}>
        <Select value={String(value)} onChange={onChange} className="w-full"
                options={p.options.map((o) => ({ value: String(o), label: String(o) }))} />
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
