import { useEffect, useState } from 'react'
import { Rocket, Play, Square, Trash2, Plus } from 'lucide-react'
import { api } from '../api/client'
import type { StrategyGroup, Deployment } from '../api/types'
import { Card, CardHeader, Button, Slider, Toggle, Select, Input, Field, Badge } from '../components/ui'
import { MultiSymbolPicker } from '../components/SymbolPicker'
import { fmt } from '../lib/utils'

export default function Deploy() {
  const [groups, setGroups] = useState<StrategyGroup[]>([])
  const [deployments, setDeployments] = useState<Deployment[]>([])
  const [name, setName] = useState('')
  const [isDemo, setIsDemo] = useState(true)
  const [bar, setBar] = useState('1H')
  const [checkIntervalPreset, setCheckIntervalPreset] = useState('3600')
  const [customInterval, setCustomInterval] = useState(3600)
  const checkIntervalSec = checkIntervalPreset === 'custom' ? customInterval : Number(checkIntervalPreset)
  const [symbols, setSymbols] = useState<string[]>(['BTC-USDT-SWAP'])
  const [instruments, setInstruments] = useState<string[]>(['BTC-USDT-SWAP', 'ETH-USDT-SWAP', 'SOL-USDT-SWAP'])
  const [leverage, setLeverage] = useState(5)
  const [positionRatio, setPositionRatio] = useState(0.1)
  const [initialCapital, setInitialCapital] = useState(10000)
  const [sel, setSel] = useState<Record<string, { weight: number; invert: boolean }>>({})
  const [msg, setMsg] = useState('')
  const [monitorId, setMonitorId] = useState('')
  const [state, setState] = useState<Record<string, unknown> | null>(null)
  const [logs, setLogs] = useState<Record<string, unknown>[]>([])

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

  async function create() {
    const groupRefs = Object.entries(sel).map(([gid, v]) => ({ group_id: gid, weight: v.weight, invert: v.invert }))
    if (!name || groupRefs.length === 0) { setMsg('需命名且选至少一组'); return }
    try {
      const d = await api.createDeployment({
        name, is_demo: isDemo, bar,
        symbols,
        groups: groupRefs, leverage, position_ratio: positionRatio, initial_capital: initialCapital,
        check_interval_sec: checkIntervalSec,
      })
      await refresh()
      setMsg(`✓ 部署「${name}」已创建 (id: ${d.id})`)
      setName('')
    } catch (e) { setMsg((e as Error).message) }
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

  const totalW = Object.values(sel).reduce((s, v) => s + v.weight, 0) || 1
  const positions = (state?.positions ?? {}) as Record<string, Record<string, number>>
  const actions = (state?.actions ?? []) as string[]
  const monitored = deployments.find((d) => d.id === monitorId)

  return (
    <div className="flex h-full">
      {/* 左：策略组库 + 已部署 */}
      <div className="w-64 shrink-0 border-r border-line p-4 overflow-auto">
        <div className="text-sm font-semibold mb-2">策略组</div>
        <div className="space-y-1 mb-6">
          {groups.map((g) => (
            <button key={g.id} onClick={() => addGroup(g.id)} disabled={!!sel[g.id]}
              className="w-full text-left px-3 py-2 rounded bg-card border border-line hover:border-accent/30 disabled:opacity-40">
              <div className="text-sm truncate">{g.name}</div>
              <div className="text-[0.7rem] text-dim">{g.spec.node_type === 'allocation_group' ? '资金分配' : '信号组合'}</div>
            </button>
          ))}
          {groups.length === 0 && <div className="text-xs text-dim">先在「策略组合」保存组</div>}
        </div>
        <div className="text-sm font-semibold mb-2">已部署</div>
        <div className="space-y-1">
          {deployments.map((d) => (
            <div key={d.id} onClick={() => setMonitorId(d.id)}
              className={`px-3 py-2 rounded border cursor-pointer ${monitorId === d.id ? 'border-accent bg-card-strong' : 'border-line bg-card hover:bg-card-strong'}`}>
              <div className="flex items-center justify-between">
                <span className="text-sm truncate">{d.name}</span>
                {d.alive ? <Badge color="up">运行</Badge> : <Badge color="dim">停止</Badge>}
              </div>
              <div className="text-[0.7rem] text-dim mt-0.5">{d.id.slice(0, 16)}</div>
            </div>
          ))}
        </div>
      </div>

      {/* 中：部署配置 */}
      <div className="w-80 shrink-0 border-r border-line p-4 overflow-auto">
        <div className="text-base font-semibold mb-3 flex items-center gap-2"><Rocket size={18} /> 新建部署</div>
        <Field label="部署名称"><Input value={name} onChange={(e) => setName(e.target.value)} className="w-full" /></Field>
        <div className="grid grid-cols-2 gap-2 mt-3">
          <Field label="模式">
            <Select value={isDemo ? 'demo' : 'live'} onChange={(v) => setIsDemo(v === 'demo')}
              options={[{ value: 'demo', label: '模拟盘' }, { value: 'live', label: '真实盘' }]} className="w-full" />
          </Field>
          <Field label="K线周期">
            <Select value={bar} onChange={setBar} options={['1H', '4H', '1D'].map((b) => ({ value: b, label: b }))} className="w-full" />
          </Field>
        </div>
        <Field label="检查间隔" hint="多长时间跑一次信号检查并调仓">
          <div className="flex gap-2 mt-1">
            <Select value={checkIntervalPreset} onChange={setCheckIntervalPreset}
              options={[
                { value: '3600', label: '1小时' },
                { value: '14400', label: '4小时' },
                { value: '86400', label: '1天' },
                { value: 'custom', label: '自定义' },
              ]} className="flex-1" />
            {checkIntervalPreset === 'custom' && (
              <Input type="number" value={customInterval} min={60}
                onChange={(e) => setCustomInterval(+e.target.value)}
                className="w-28" placeholder="秒数" />
            )}
          </div>
        </Field>
        <Field label="品种（单币策略批量运行）" hint="单币策略会对所选每个币种独立运行">
          <MultiSymbolPicker value={symbols} onChange={setSymbols} instruments={instruments} />
        </Field>
        <div className="grid grid-cols-3 gap-2 mt-3">
          <Field label="杠杆"><Input type="number" value={leverage} onChange={(e) => setLeverage(+e.target.value)} className="w-full" /></Field>
          <Field label="仓位%"><Input type="number" step="0.01" value={positionRatio} onChange={(e) => setPositionRatio(+e.target.value)} className="w-full" /></Field>
          <Field label="资金"><Input type="number" value={initialCapital} onChange={(e) => setInitialCapital(+e.target.value)} className="w-full" /></Field>
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
        <Button variant="primary" className="w-full mt-4" onClick={create}><Plus size={15} className="inline mr-1.5" />创建部署</Button>
        {msg && <div className="text-xs text-accent mt-2 break-all">{msg}</div>}
      </div>

      {/* 右：监控 */}
      <div className="flex-1 p-4 overflow-auto">
        {monitorId && monitored ? (
          <>
            <div className="flex items-center justify-between mb-3">
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
          <div className="text-dim text-sm py-20 text-center">选择左侧部署查看实时监控</div>
        )}
      </div>
    </div>
  )
}
