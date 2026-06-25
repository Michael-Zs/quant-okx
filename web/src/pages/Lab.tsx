import { useEffect, useMemo, useState } from 'react'
import { Save, Trash2, Search, Bot, RefreshCw, FileCode2 } from 'lucide-react'
import { api } from '../api/client'
import type { TemplateInfo, UserStrategy, GridSearchResult } from '../api/types'
import { Card, CardHeader, Button, Input, Field, Badge } from '../components/ui'
import { pct, fmt } from '../lib/utils'
import { SpecModal } from '../components/SpecModal'

const SINGLE_TEMPLATE = (name: string, cls: string) => `"""自定义策略：${name}"""
import pandas as pd
from core.strategy.base import Strategy, Param


class ${cls}(Strategy):
    name = "${name}"
    display_name = "${name}"
    description = "自定义策略"
    side_mode = "long_short"

    # 参数声明示例（UI 会自动生成控件）：
    # period = Param("period", 14, 2, 100, 1, label="周期")

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        close = df["close"]
        # TODO: 编写策略逻辑，输出 signal 列（1 做多 / -1 做空 / 0 空仓）
        df["signal"] = 0
        df["trade"] = df["signal"].diff().fillna(0).astype(int)
        return df
`

const clsName = (n: string) => n.split('_').map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join('') || 'MyStrategy'

const IDENT = /^[a-zA-Z_][a-zA-Z0-9_]*$/

export default function Lab() {
  const [tab, setTab] = useState<'edit' | 'grid'>('edit')

  return (
    <div className="flex flex-col h-full">
      <div className="px-6 pt-5 pb-3 border-b border-line flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight flex items-center gap-2">
            <Bot size={20} className="text-accent" /> 策略实验室
          </h1>
          <p className="text-xs text-dim mt-0.5">用 Python 写策略，保存即注册即用；参数网格搜索找最优组合。</p>
        </div>
        <div className="flex gap-1 p-1 bg-black/20 rounded-sm">
          {(['edit', 'grid'] as const).map((k) => (
            <button key={k} onClick={() => setTab(k)}
              className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${tab === k ? 'bg-card-strong text-accent' : 'text-dim hover:text-text'}`}>
              {k === 'edit' ? '✏️ 代码编辑器' : '🔬 网格搜索'}
            </button>
          ))}
        </div>
      </div>
      <div className="flex-1 overflow-auto">
        {tab === 'edit' ? <EditorTab /> : <GridTab />}
      </div>
    </div>
  )
}

// ============ 编辑器 ============

function EditorTab() {
  const [files, setFiles] = useState<UserStrategy[]>([])
  const [sel, setSel] = useState<string>('')
  const [name, setName] = useState('my_strategy')
  const [code, setCode] = useState(SINGLE_TEMPLATE('my_strategy', 'MyStrategy'))
  const [dirty, setDirty] = useState(false)
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)
  const [specOpen, setSpecOpen] = useState(false)

  async function refresh() {
    const r = await api.userStrategies()
    setFiles(r.files)
    if (r.files.length && !sel) loadFile(r.files[r.files.length - 1])
  }
  useEffect(() => { refresh() }, [])

  function loadFile(f: UserStrategy) {
    setSel(f.name); setName(f.name); setCode(f.code); setDirty(false); setMsg(null)
  }

  function newFile() {
    setSel(''); setName('my_strategy')
    setCode(SINGLE_TEMPLATE('my_strategy', 'MyStrategy')); setDirty(false); setMsg(null)
  }

  async function save() {
    if (!IDENT.test(name)) { setMsg({ kind: 'err', text: '策略名必须是合法 Python 标识符（字母/数字/下划线，不以数字开头）' }); return }
    try {
      const r = await api.saveUserStrategy({ name, code })
      setMsg(r.registered
        ? { kind: 'ok', text: `✔ 已保存并注册：${name}（共 ${r.names.length} 个策略）` }
        : { kind: 'err', text: '保存了文件，但注册失败——代码可能有语法错误或未定义 Strategy 子类。查看终端日志。' })
      setDirty(false); setSel(name); await refresh()
    } catch (e) { setMsg({ kind: 'err', text: (e as Error).message }) }
  }

  async function del() {
    if (!sel) return
    if (!confirm(`确定删除 ${sel}.py？`)) return
    try {
      await api.deleteUserStrategy(sel)
      setMsg({ kind: 'ok', text: `已删除 ${sel}` })
      newFile(); await refresh()
    } catch (e) { setMsg({ kind: 'err', text: (e as Error).message }) }
  }

  return (
    <div className="flex h-full">
      {/* 左：文件列表 */}
      <div className="w-60 shrink-0 border-r border-line p-3 overflow-auto">
        <button onClick={newFile}
          className="w-full mb-3 flex items-center justify-center gap-1.5 py-1.5 rounded text-xs font-medium border border-accent/30 text-accent hover:bg-accent/10">
          + 新建策略
        </button>
        <button onClick={refresh} className="w-full mb-3 flex items-center justify-center gap-1.5 py-1.5 rounded text-xs text-dim hover:text-text hover:bg-card">
          <RefreshCw size={12} /> 刷新
        </button>
        <div className="text-[0.7rem] uppercase tracking-wider text-dim mb-1.5 px-1">用户策略文件</div>
        <div className="space-y-0.5">
          {files.length === 0 ? (
            <div className="text-xs text-dim px-1 py-2">暂无文件</div>
          ) : files.map((f) => (
            <button key={f.name} onClick={() => loadFile(f)}
              className={`w-full text-left px-2 py-1.5 rounded text-xs flex items-center gap-1.5 ${sel === f.name ? 'bg-card-strong text-accent' : 'text-dim hover:text-text hover:bg-card'}`}>
              <FileCode2 size={13} className="shrink-0" />
              <span className="truncate">{f.name}</span>
            </button>
          ))}
        </div>
      </div>

      {/* 中+右：编辑器 */}
      <div className="flex-1 flex flex-col min-w-0">
        <div className="p-4 border-b border-line space-y-3">
          <div className="flex items-end gap-3">
            <Field label="策略名（英文标识符，作为文件名与 registry key）">
              <Input value={name} onChange={(e) => { setName(e.target.value); setDirty(true) }}
                     className="w-72" spellCheck={false} />
            </Field>
            <div className="flex gap-2">
              <Button variant="primary" onClick={save} disabled={!dirty && !!sel}>
                <Save size={15} className="inline mr-1.5" />保存并注册
              </Button>
              <Button variant="danger" onClick={del} disabled={!sel}>
                <Trash2 size={15} className="inline mr-1.5" />删除
              </Button>
              <Button variant="ghost" onClick={() => setSpecOpen(true)}>
                <Bot size={15} className="inline mr-1.5" />AI 规范
              </Button>
            </div>
          </div>
          <div className="text-xs text-warn bg-warn/5 border border-warn/20 rounded px-3 py-1.5">
            ⚠ 策略代码拥有完整 Python 权限（与本程序相同），请仅在自己机器上运行可信代码。
          </div>
          {msg && (
            <div className={`text-xs rounded px-3 py-1.5 ${msg.kind === 'ok' ? 'text-up bg-up/5 border border-up/20' : 'text-down bg-down/5 border border-down/20'}`}>
              {msg.text}
            </div>
          )}
        </div>
        <div className="flex-1 min-h-0 p-4">
          <CodeEditor value={code} onChange={(v) => { setCode(v); setDirty(true) }} />
        </div>
      </div>
      {specOpen && <SpecModal kind="single" onClose={() => setSpecOpen(false)} />}
    </div>
  )
}

function CodeEditor({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  // 同步行高 + tab 缩进。轻量方案：textarea + 等宽字体。未来可换 Monaco/CodeMirror。
  const lines = value.split('\n').length
  return (
    <div className="h-full rounded border border-line bg-[#0a0e17] overflow-hidden flex">
      <div className="select-none text-right py-3 px-2 text-[0.7rem] text-dim/50 font-mono bg-black/30 border-r border-line overflow-hidden">
        {Array.from({ length: Math.max(lines, 20) }, (_, i) => (
          <div key={i} style={{ lineHeight: '1.5' }}>{i + 1}</div>
        ))}
      </div>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Tab') {
            e.preventDefault()
            const t = e.currentTarget
            const start = t.selectionStart, end = t.selectionEnd
            const nv = value.slice(0, start) + '    ' + value.slice(end)
            onChange(nv)
            requestAnimationFrame(() => { t.selectionStart = t.selectionEnd = start + 4 })
          }
        }}
        spellCheck={false}
        className="flex-1 resize-none bg-transparent text-[0.8rem] font-mono text-text p-3 outline-none leading-[1.5]"
        style={{ tabSize: 4 }}
      />
    </div>
  )
}

// ============ 网格搜索 ============

const METRICS = ['total_return', 'sharpe', 'calmar', 'sortino'] as const

function GridTab() {
  const [templates, setTemplates] = useState<TemplateInfo[]>([])
  const [sel, setSel] = useState('')
  const [ranges, setRanges] = useState<Record<string, [number, number, number]>>({})
  const [symbol, setSymbol] = useState('BTC-USDT-SWAP')
  const [bar, setBar] = useState('1H')
  const [days, setDays] = useState(180)
  const [metric, setMetric] = useState<typeof METRICS[number]>('sharpe')
  const [jobs, setJobs] = useState(1)
  const [loading, setLoading] = useState(false)
  const [results, setResults] = useState<GridSearchResult[]>([])
  const [keys, setKeys] = useState<string[]>([])
  const [usedMetric, setUsedMetric] = useState('sharpe')
  const [err, setErr] = useState('')

  useEffect(() => {
    api.templates().then((r) => {
      const t = r.templates.filter((x) => x.strategy_kind === 'single')
      setTemplates(t)
      if (t[0]) setSel(t[0].name)
    })
  }, [])

  const tpl = templates.find((t) => t.name === sel)
  useEffect(() => {
    if (!tpl) return
    const r: Record<string, [number, number, number]> = {}
    for (const p of tpl.params) {
      if (p.kind === 'select') continue
      const d = Number(p.default)
      const hi = p.max ?? d * 2
      const lo = p.min ?? d
      const st = p.step ?? 1
      r[p.name] = [lo, hi, st]
    }
    setRanges(r)
  }, [sel, tpl])

  const total = useMemo(() => {
    let n = 1
    for (const [lo, hi, st] of Object.values(ranges)) {
      const cnt = Math.max(1, Math.floor((hi - lo) / Math.max(st, 1e-9)) + 1)
      n *= cnt
    }
    return n
  }, [ranges])

  async function run() {
    setLoading(true); setErr('')
    try {
      const r = await api.gridSearch({ template_name: sel, param_ranges: ranges, symbol, bar, days, metric, n_jobs: jobs })
      setResults(r.results); setKeys(r.keys); setUsedMetric(r.metric)
    } catch (e) { setErr((e as Error).message) }
    finally { setLoading(false) }
  }

  const numericParams = tpl?.params.filter((p) => p.kind !== 'select') ?? []

  return (
    <div className="flex h-full">
      {/* 左：配置 */}
      <div className="w-80 shrink-0 border-r border-line p-4 overflow-auto">
        {tpl ? (
          <>
            <Field label="策略">
              <select value={sel} onChange={(e) => setSel(e.target.value)}
                className="w-full px-3 py-2 rounded-sm bg-black/30 border border-line text-sm text-text outline-none focus:border-accent">
                {templates.map((t) => <option key={t.name} value={t.name} className="bg-bg2">{t.display_name}</option>)}
              </select>
            </Field>
            <div className="grid grid-cols-2 gap-2 mt-3">
              <Field label="品种"><Input value={symbol} onChange={(e) => setSymbol(e.target.value)} className="w-full" spellCheck={false} /></Field>
              <Field label="周期">
                <select value={bar} onChange={(e) => setBar(e.target.value)} className="w-full px-3 py-2 rounded-sm bg-black/30 border border-line text-sm outline-none">
                  {['1H', '4H', '1D'].map((b) => <option key={b} className="bg-bg2">{b}</option>)}
                </select>
              </Field>
            </div>
            <div className="grid grid-cols-2 gap-2 mt-2">
              <Field label="回测天数"><Input type="number" value={days} onChange={(e) => setDays(+e.target.value)} className="w-full" /></Field>
              <Field label="并行进程"><Input type="number" value={jobs} min={1} max={8} onChange={(e) => setJobs(+e.target.value)} className="w-full" /></Field>
            </div>
            <div className="h-px bg-line my-4" />
            <div className="text-xs text-dim mb-2">参数搜索范围（仅数值参数）</div>
            {numericParams.length === 0 ? (
              <div className="text-xs text-dim italic">该策略无数值参数可搜索</div>
            ) : numericParams.map((p) => (
              <div key={p.name} className="mb-3">
                <div className="text-xs text-text mb-1">{p.label || p.name}</div>
                <div className="grid grid-cols-3 gap-1">
                  {(['起', '止', '步'] as const).map((lab, i) => (
                    <label key={lab} className="block">
                      <span className="text-[0.65rem] text-dim">{lab}</span>
                      <Input type="number" step="any" value={ranges[p.name]?.[i] ?? 0}
                        onChange={(e) => setRanges((s) => {
                          const cur = [...(s[p.name] ?? [0, 0, 1])] as [number, number, number]
                          cur[i] = +e.target.value; return { ...s, [p.name]: cur }
                        })}
                        className="w-full text-xs px-2 py-1" />
                    </label>
                  ))}
                </div>
              </div>
            ))}
            <div className="h-px bg-line my-4" />
            <Field label="优化目标">
              <select value={metric} onChange={(e) => setMetric(e.target.value as typeof METRICS[number])}
                className="w-full px-3 py-2 rounded-sm bg-black/30 border border-line text-sm outline-none">
                {METRICS.map((m) => <option key={m} value={m} className="bg-bg2">{m}</option>)}
              </select>
            </Field>
            <div className="text-xs text-dim mt-3">将测试 <span className="text-accent font-semibold">{total}</span> 个组合</div>
            <Button variant="primary" className="w-full mt-3" onClick={run} disabled={loading || total === 0 || numericParams.length === 0}>
              <Search size={15} className="inline mr-1.5" />{loading ? '搜索中…' : '开始搜索'}
            </Button>
            {err && <div className="text-xs text-down mt-2 break-all">{err}</div>}
          </>
        ) : <div className="text-dim text-sm">加载中…</div>}
      </div>

      {/* 右：结果 */}
      <div className="flex-1 overflow-auto p-4">
        {results.length === 0 ? (
          <div className="text-dim text-sm py-16 text-center">配置参数范围后点「开始搜索」</div>
        ) : (
          <>
            <Card>
              <CardHeader title={`🏆 Top 结果（按 ${usedMetric} 降序）`}
                subtitle={`${results.length} 个组合 · ${tpl?.display_name} · ${symbol} ${bar} ${days}天`}
                action={<Badge color="accent">最佳 {fmt(results[0][usedMetric] as number, 3)}</Badge>} />
              <div className="overflow-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-dim border-b border-line">
                      <th className="text-left px-3 py-2 font-medium">#</th>
                      {keys.map((k) => <th key={k} className="text-left px-3 py-2 font-medium">{k}</th>)}
                      <th className="text-right px-3 py-2 font-medium">总收益</th>
                      <th className="text-right px-3 py-2 font-medium">夏普</th>
                      <th className="text-right px-3 py-2 font-medium">回撤</th>
                      <th className="text-right px-3 py-2 font-medium">卡尔玛</th>
                      <th className="text-right px-3 py-2 font-medium">胜率</th>
                      <th className="text-right px-3 py-2 font-medium">交易</th>
                    </tr>
                  </thead>
                  <tbody>
                    {results.slice(0, 50).map((r, i) => (
                      <tr key={i} className={`border-b border-line/40 hover:bg-card ${i === 0 ? 'bg-accent/5' : ''}`}>
                        <td className="px-3 py-1.5 text-dim">{i + 1}</td>
                        {keys.map((k) => <td key={k} className="px-3 py-1.5 font-mono">{typeof r[k] === 'number' || typeof r[k] === 'string' ? r[k] : ''}</td>)}
                        <td className={`px-3 py-1.5 text-right tnum ${r.total_return >= 0 ? 'text-up' : 'text-down'}`}>{pct(r.total_return)}</td>
                        <td className="px-3 py-1.5 text-right tnum">{fmt(r.sharpe)}</td>
                        <td className="px-3 py-1.5 text-right tnum text-down">{pct(r.max_drawdown)}</td>
                        <td className="px-3 py-1.5 text-right tnum">{fmt(r.calmar)}</td>
                        <td className="px-3 py-1.5 text-right tnum">{pct(r.win_rate)}</td>
                        <td className="px-3 py-1.5 text-right tnum text-dim">{r.n_trades}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
            <div className="text-xs text-dim/70 mt-2">显示前 50 条；可通过调整范围或优化目标重新搜索。</div>
          </>
        )}
      </div>
    </div>
  )
}
