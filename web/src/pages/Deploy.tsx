import { useEffect, useState } from 'react'
import { Rocket, Play, Square, Trash2, Plus, TrendingUp, ChevronRight, Activity } from 'lucide-react'
import { api } from '../api/client'
import type { StrategyGroup, Deployment, BacktestMetrics, SampledSeries, NodeSpec, ExecutorState } from '../api/types'
import { Card, CardHeader, Button, Slider, Toggle, Select, Input, Field, Badge } from '../components/ui'
import { EquityChart, MetricsGrid } from '../components/charts'
import { MultiSymbolPicker } from '../components/SymbolPicker'
import { fmt } from '../lib/utils'

export default function Deploy() {
  const [groups, setGroups] = useState<StrategyGroup[]>([])
  const [deployments, setDeployments] = useState<Deployment[]>([])
  const [name, setName] = useState('')
  const [isDemo, setIsDemo] = useState(true)
  const [bar, setBar] = useState('1H')
  const [symbols, setSymbols] = useState<string[]>(['BTC-USDT-SWAP'])
  const [instruments, setInstruments] = useState<string[]>(['BTC-USDT-SWAP', 'ETH-USDT-SWAP', 'SOL-USDT-SWAP'])
  const [leverage, setLeverage] = useState(5)
  const [positionRatio, setPositionRatio] = useState(0.1)
  const [capitalWeight, setCapitalWeight] = useState(1.0)
  const [initialCapital, setInitialCapital] = useState(10000)
  const [sel, setSel] = useState<Record<string, { weight: number; invert: boolean }>>({})
  const [msg, setMsg] = useState('')
  const [monitorId, setMonitorId] = useState('')
  const [state, setState] = useState<Record<string, unknown> | null>(null)
  const [logs, setLogs] = useState<Record<string, unknown>[]>([])
  const [editingDeployId, setEditingDeployId] = useState<string | null>(null)
  const [btResult, setBtResult] = useState<{ metrics: BacktestMetrics; equity?: SampledSeries; benchmark?: SampledSeries; n_trades?: number } | null>(null)
  const [btLoading, setBtLoading] = useState(false)
  const [btDays, setBtDays] = useState(180)
  const [btCollapsed, setBtCollapsed] = useState(false)
  const [executorState, setExecutorState] = useState<ExecutorState | null>(null)

  useEffect(() => {
    refresh()
    api.instruments().then((r) => setInstruments(r.instruments)).catch(() => {})
  }, [])
  async function refresh() {
    const [g, d] = await Promise.all([api.listGroups(), api.listDeployments()])
    setGroups(g.groups); setDeployments(d.deployments)
  }

  function addGroup(gid: string) {
    setSel((s) => (s[gid] ? s : { ...s, [gid]: { weight: 1, invert: false } }))
  }
  function updateSel(gid: string, patch: Partial<{ weight: number; invert: boolean }>) {
    setSel((s) => ({ ...s, [gid]: { ...s[gid], ...patch } }))
  }
  function removeSel(gid: string) {
    setSel((s) => { const n = { ...s }; delete n[gid]; return n })
  }

  function loadDeployment(d: Deployment) {
    setEditingDeployId(d.id)
    setMonitorId(d.id)
    setName(d.name); setIsDemo(d.is_demo); setBar(d.bar); setSymbols(d.symbols)
    setLeverage(d.leverage); setPositionRatio(d.position_ratio)
    setCapitalWeight(d.capital_weight ?? 1.0)
    const next: Record<string, { weight: number; invert: boolean }> = {}
    for (const g of d.groups) next[g.group_id] = { weight: g.weight, invert: g.invert }
    setSel(next)
    setBtResult(null); setMsg('')
  }

  function newDeploy() {
    setEditingDeployId(null); setMonitorId('')
    setName(''); setSel({})
    setIsDemo(true); setBar('1H'); setSymbols(['BTC-USDT-SWAP'])
    setLeverage(5); setPositionRatio(0.1); setCapitalWeight(1.0); setInitialCapital(10000)
    setBtResult(null); setMsg('')
  }

  async function save() {
    const groupRefs = Object.entries(sel).map(([gid, v]) => ({ group_id: gid, weight: v.weight, invert: v.invert }))
    if (!name || groupRefs.length === 0) { setMsg('需命名且选至少一组'); return }
    try {
      const payload = { name, is_demo: isDemo, bar, symbols,
        groups: groupRefs, leverage, position_ratio: positionRatio,
        capital_weight: capitalWeight }
      if (editingDeployId) {
        await api.updateDeployment(editingDeployId, payload)
        setMsg(`✓ 已更新部署「${name}」`)
      } else {
        const d = await api.createDeployment(payload)
        setEditingDeployId(d.id); setMonitorId(d.id)
        setMsg(`✓ 部署「${name}」已创建 (id: ${d.id})`)
      }
      await refresh()
    } catch (e) { setMsg((e as Error).message) }
  }

  async function runBacktest() {
    if (Object.keys(sel).length === 0) { setMsg('请先选择至少一个策略组'); return }
    setBtLoading(true); setMsg('')
    try {
      const common = { symbols, bar, leverage, position_ratio: positionRatio,
        initial_capital: initialCapital, days: btDays, response_mode: 'full' as const }
      let r
      if (editingDeployId) {
        r = await api.backtest({ ref_kind: 'deployment', ref_id: editingDeployId, ...common })
      } else {
        // 新建态：把当前所选组就地组装成 allocation_group node_spec 回测
        const children = Object.entries(sel)
          .map(([gid, v]) => ({ node: groups.find((g) => g.id === gid)?.spec, weight: v.weight, invert: v.invert }))
          .filter((c): c is { node: NodeSpec; weight: number; invert: boolean } => !!c.node)
        const node_spec: NodeSpec = { node_type: 'allocation_group', name: name || 'preview', invert: false, children }
        r = await api.backtest({ node_spec, ...common })
      }
      setBtResult(r as { metrics: BacktestMetrics; equity?: SampledSeries; benchmark?: SampledSeries; n_trades?: number })
      setBtCollapsed(false)
    } catch (e) { setMsg((e as Error).message) }
    finally { setBtLoading(false) }
  }

  async function start(id: string) { await api.startDeployment(id); setTimeout(refresh, 600); setMonitorId(id) }
  async function stop(id: string) { await api.stopDeployment(id); setTimeout(refresh, 600) }
  async function del(id: string) { await api.deleteDeployment(id); if (monitorId === id) setMonitorId(''); refresh() }

  // 监控轮询（5s）
  useEffect(() => {
    if (!monitorId) return
    let stopped = false
    async function poll() {
      try {
        const [s, l] = await Promise.all([api.deploymentState(monitorId), api.deploymentLogs(monitorId)])
        if (!stopped) { setState(s); setLogs(l.logs) }
      } catch { /* ignore */ }
    }
    poll()
    const t = setInterval(poll, 5000)
    return () => { stopped = true; clearInterval(t) }
  }, [monitorId])

  // Executor 状态轮询（10s）
  useEffect(() => {
    let stopped = false
    async function pollExecutor() {
      try {
        const es = await api.executorState()
        if (!stopped) setExecutorState(es)
      } catch { /* ignore */ }
    }
    pollExecutor()
    const t = setInterval(pollExecutor, 10000)
    return () => { stopped = true; clearInterval(t) }
  }, [])

  const totalW = Object.values(sel).reduce((s, v) => s + v.weight, 0) || 1
  const positions = (state?.positions ?? {}) as Record<string, Record<string, number>>
  const actions = (state?.actions ?? []) as string[]
  const monitored = deployments.find((d) => d.id === monitorId)

  return (
    <div className="flex flex-col md:flex-row md:h-full">
      {/* 左：策略组库 + 已部署 */}
      <div className="w-full md:w-64 md:shrink-0 border-b md:border-b-0 md:border-r border-line p-4 md:overflow-auto">
        <details open className="mb-4 group">
          <summary className="text-sm font-semibold cursor-pointer flex items-center gap-1.5 list-none [&::-webkit-details-marker]:hidden">
            <ChevronRight size={14} className="text-dim transition-transform group-open:rotate-90" />
            策略组
          </summary>
          <div className="space-y-1 mt-2">
            {groups.map((g) => (
              <button key={g.id} onClick={() => addGroup(g.id)} disabled={!!sel[g.id]}
                className="w-full text-left px-3 py-2 rounded bg-card border border-line hover:border-accent/30 disabled:opacity-40">
                <div className="text-sm truncate">{g.name}</div>
                <div className="text-[0.7rem] text-dim">{g.spec.node_type === 'allocation_group' ? '资金分配' : '信号组合'}</div>
              </button>
            ))}
            {groups.length === 0 && <div className="text-xs text-dim">先在「策略组合」保存组</div>}
          </div>
        </details>

        <details open className="group">
          <summary className="text-sm font-semibold cursor-pointer flex items-center gap-1.5 list-none [&::-webkit-details-marker]:hidden">
            <ChevronRight size={14} className="text-dim transition-transform group-open:rotate-90" />
            已部署
          </summary>
          <div className="space-y-1 mt-2">
            {deployments.map((d) => (
              <div key={d.id} onClick={() => loadDeployment(d)}
                className={`px-3 py-2 rounded border cursor-pointer ${monitorId === d.id ? 'border-accent bg-card-strong' : 'border-line bg-card hover:bg-card-strong'}`}>
                <div className="flex items-center justify-between">
                  <span className="text-sm truncate">{d.name}</span>
                  {d.alive ? <Badge color="up">运行</Badge> : <Badge color="dim">停止</Badge>}
                </div>
                <div className="text-[0.7rem] text-dim mt-0.5">{d.id.slice(0, 16)}</div>
              </div>
            ))}
          </div>
        </details>
      </div>

      {/* 中：部署配置 */}
      <div className="w-full md:w-80 md:shrink-0 border-b md:border-b-0 md:border-r border-line p-4 md:overflow-auto">
        <div className="flex items-center justify-between mb-3">
          <div className="text-base font-semibold flex items-center gap-2"><Rocket size={18} />{editingDeployId ? '编辑部署' : '新建部署'}</div>
          {editingDeployId && <button onClick={newDeploy} className="text-xs text-accent hover:underline">+ 新建</button>}
        </div>
        <Field label="部署名称"><Input value={name} onChange={(e) => setName(e.target.value)} className="w-full" /></Field>
        <div className="grid grid-cols-2 gap-2 mt-3">
          <Field label="模式">
            <Select value={isDemo ? 'demo' : 'live'} onChange={(v) => setIsDemo(v === 'demo')}
              options={[{ value: 'demo', label: '模拟盘' }, { value: 'live', label: '真实盘' }]} className="w-full" />
          </Field>
          <Field label="周期" hint="选1H→每小时跑，4H→每4小时，1D→每天">
            <Select value={bar} onChange={setBar} options={['1H', '4H', '1D'].map((b) => ({ value: b, label: b }))} className="w-full" />
          </Field>
        </div>
        <Field label="品种（单币策略批量运行）" hint="单币策略会对所选每个币种独立运行">
          <MultiSymbolPicker value={symbols} onChange={setSymbols} instruments={instruments} />
        </Field>
        <div className="grid grid-cols-2 gap-2 mt-3">
          <Field label="杠杆"><Input type="number" value={leverage} onChange={(e) => setLeverage(+e.target.value)} className="w-full" /></Field>
          <Field label="仓位%"><Input type="number" step="0.01" value={positionRatio} onChange={(e) => setPositionRatio(+e.target.value)} className="w-full" /></Field>
        </div>
        <div className="mt-3">
          <Field label="资金份额" hint="多部署时分账户份额，Σ≤1；单部署填 1.0">
            <Input type="number" step="0.01" min={0} max={1} value={capitalWeight} onChange={(e) => setCapitalWeight(+e.target.value)} className="w-full" />
          </Field>
        </div>
        <div className="h-px bg-line my-4" />
        <div className="text-xs text-dim mb-1">策略组占比（资金层分配）</div>
        <div className="text-[0.7rem] text-dim/70 mb-2">滑块调资金占比；开关=「反向」，反转该组信号方向（1↔-1），可用于翻转亏损策略或对冲配置</div>
        <div className="space-y-2">
          {Object.entries(sel).map(([gid, v]) => {
            const g = groups.find((x) => x.id === gid)
            return (
              <div key={gid} className="p-2.5 rounded bg-card border border-line">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm truncate flex-1">{g?.name || gid.slice(0, 8)}</span>
                  <button onClick={() => removeSel(gid)} className="text-dim hover:text-down ml-2"><Trash2 size={14} /></button>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-dim w-10 tnum">{((v.weight / totalW) * 100).toFixed(0)}%</span>
                  <Slider value={v.weight} min={0} max={5} step={0.1} onChange={(w) => updateSel(gid, { weight: w })} className="flex-1" />
                  <span title="反向：反转该策略组的信号方向（做多↔做空）">
                    <Toggle checked={v.invert} onChange={(inv) => updateSel(gid, { invert: inv })} label="反向" />
                  </span>
                </div>
              </div>
            )
          })}
          {Object.keys(sel).length === 0 && <div className="text-xs text-dim">从左侧选策略组</div>}
        </div>
        <div className="grid grid-cols-2 gap-2 mt-3">
          <Field label="回测天数" hint="回测预览用"><Input type="number" value={btDays} onChange={(e) => setBtDays(+e.target.value)} className="w-full" /></Field>
          <Field label="回测资金" hint="起始资金（实盘用账户实际权益）"><Input type="number" value={initialCapital} onChange={(e) => setInitialCapital(+e.target.value)} className="w-full" /></Field>
        </div>
        <div className="grid grid-cols-2 gap-2 mt-3">
          <Button variant="primary" className="py-2.5 md:py-2" onClick={save}><Plus size={15} className="inline mr-1.5" />{editingDeployId ? '更新部署' : '创建部署'}</Button>
          <Button variant="ghost" className="py-2.5 md:py-2" onClick={runBacktest} disabled={btLoading}><TrendingUp size={15} className="inline mr-1.5" />{btLoading ? '回测中…' : '回测预览'}</Button>
        </div>
        {editingDeployId && deployments.find((d) => d.id === editingDeployId)?.alive && (
          <div className="text-[0.7rem] text-accent mt-2">部署运行中：修改需停止再启动才生效</div>
        )}
        {msg && <div className="text-xs text-accent mt-2 break-all">{msg}</div>}
      </div>

      {/* 右：监控 */}
      <div className="w-full md:flex-1 p-4 md:overflow-auto">
        {btResult && (
          <Card className="mb-4">
            <div className="flex items-center justify-between px-4 pt-4">
              <div>
                <div className="text-sm font-semibold">📈 回测预览</div>
                <div className="text-[0.7rem] text-dim">{symbols.join(', ')} · {bar} · {btDays}天{editingDeployId ? '' : ' · 未保存配置'}</div>
              </div>
              <button onClick={() => setBtCollapsed((c) => !c)} className="text-xs text-dim hover:text-accent">{btCollapsed ? '展开' : '收起'}</button>
            </div>
            {!btCollapsed && (
              <>
                <div className="px-4 pb-4"><EquityChart equity={btResult.equity ?? null} benchmark={btResult.benchmark ?? null} /></div>
                <div className="px-4 pb-4"><MetricsGrid m={btResult.metrics} /></div>
              </>
            )}
          </Card>
        )}
        {/* Executor 状态卡 */}
        {executorState && (executorState.demo || executorState.live) && (
          <Card className="mb-4">
            <div className="flex items-center gap-2 px-4 pt-4">
              <Activity size={16} className="text-accent" />
              <div className="text-sm font-semibold">Executor 聚合对账</div>
              <div className="text-[0.7rem] text-dim ml-auto">
                部署数: demo={executorState.deployment_count?.demo ?? 0} live={executorState.deployment_count?.live ?? 0}
              </div>
            </div>
            <div className="p-4 pt-2 space-y-3">
              {executorState.demo && !('error' in executorState.demo) && (
                <div>
                  <div className="text-xs text-dim mb-1">模拟盘 · 权益 {fmt(executorState.demo.equity)}</div>
                  {executorState.demo.warn && <div className="text-xs text-warn mb-1">⚠ {executorState.demo.warn}</div>}
                  {executorState.demo.actions?.length > 0 && (
                    <div className="text-xs text-dim truncate">{executorState.demo.actions.slice(0, 3).join(' · ')}{executorState.demo.actions.length > 3 ? '...' : ''}</div>
                  )}
                </div>
              )}
              {executorState.live && !('error' in executorState.live) && (
                <div>
                  <div className="text-xs text-dim mb-1">实盘 · 权益 {fmt(executorState.live.equity)}</div>
                  {executorState.live.warn && <div className="text-xs text-warn mb-1">⚠ {executorState.live.warn}</div>}
                  {executorState.live.actions?.length > 0 && (
                    <div className="text-xs text-dim truncate">{executorState.live.actions.slice(0, 3).join(' · ')}{executorState.live.actions.length > 3 ? '...' : ''}</div>
                  )}
                </div>
              )}
            </div>
          </Card>
        )}
        {monitorId && monitored ? (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
              <div className="text-base font-semibold">监控 · {monitored.name}</div>
              <div className="flex gap-2">
                <Button variant="primary" onClick={() => start(monitorId)} disabled={!!monitored.alive}><Play size={14} className="inline mr-1" />启动{monitored.alive ? '（已运行）' : ''}</Button>
                <Button variant="danger" onClick={() => stop(monitorId)}><Square size={14} className="inline mr-1" />停止</Button>
                <Button variant="ghost" onClick={() => del(monitorId)}><Trash2 size={14} /></Button>
              </div>
            </div>
            {state && (
              <Card className="mb-4">
                <CardHeader title="持仓与状态" subtitle={`权益 ${fmt((state.equity ?? state.balance) as number)}${state.equity == null ? ' (可用)' : ''} · ${String(state.status ?? '')}`} />
                <div className="p-4 pt-0">
                  {Object.entries(positions).map(([sym, p]) => (
                    <div key={sym} className="flex items-center justify-between py-1.5 border-b border-line last:border-0">
                      <span className="text-sm">{sym}</span>
                      <span className="text-xs text-dim tnum">
                        目标 {fmt(p.target_notional, 0)} · 当前 {fmt(p.current_notional, 0)} · 浮盈 {fmt(p.unrealized_pnl)}
                      </span>
                    </div>
                  ))}
                  {actions.length > 0 && <div className="mt-2 text-xs text-accent">{actions.join(' · ')}</div>}
                </div>
              </Card>
            )}
            <Card>
              <CardHeader title="事件日志" />
              <div className="p-4 pt-0 space-y-1 max-h-96 overflow-auto">
                {logs.map((l, i) => (
                  <div key={i} className="text-xs font-mono text-dim">
                    <span className="text-dim/70">{String(l.ts ?? '')}</span>{' '}
                    <span className={l.event === 'error' ? 'text-down' : 'text-text'}>{String(l.event ?? '')}</span>{' '}
                    {l.actions ? JSON.stringify(l.actions) : (l.error ? String(l.error) : '')}
                  </div>
                ))}
                {logs.length === 0 && <div className="text-xs text-dim">无日志</div>}
              </div>
            </Card>
          </>
        ) : (
          <div className="text-dim text-sm py-20 text-center">{btResult ? '' : '选择左侧部署查看实时监控，或点「回测预览」'}</div>
        )}
      </div>
    </div>
  )
}
