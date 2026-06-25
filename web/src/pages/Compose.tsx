import { useEffect, useRef, useState } from 'react'
import { DndContext, useDraggable, useDroppable, useSensor, useSensors, PointerSensor, closestCenter, type DragEndEvent } from '@dnd-kit/core'
import { SortableContext, useSortable, arrayMove, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { GripVertical, Trash2, Plus, Save } from 'lucide-react'
import { api, openBacktestWS } from '../api/client'
import type { StrategyInstance, NodeSpec, ChildRefSpec, BacktestMetrics } from '../api/types'
import { Card, CardHeader, Button, Slider, Toggle, Select, Input, Field } from '../components/ui'
import { EquityChart, MetricsGrid } from '../components/charts'
import { MultiSymbolPicker } from '../components/SymbolPicker'
import { useStore } from '../store/useStore'
import { uid } from '../lib/utils'

interface EditChild { _id: string; node: NodeSpec; weight: number; invert: boolean }
type GroupType = 'allocation_group' | 'signal_combiner'

export default function Compose() {
  const [strategies, setStrategies] = useState<StrategyInstance[]>([])
  const [groupType, setGroupType] = useState<GroupType>('allocation_group')
  const [mode, setMode] = useState('vote')
  const [children, setChildren] = useState<EditChild[]>([])
  const [groupName, setGroupName] = useState('')
  const [msg, setMsg] = useState('')
  const [metrics, setMetrics] = useState<BacktestMetrics | null>(null)
  const [equity, setEquity] = useState<{ ts: string[]; equity: number[] } | null>(null)
  const [benchmark, setBenchmark] = useState<{ ts: string[]; equity: number[] } | null>(null)
  // 回测预览参数（此前硬编码为 1H/180天/BTC）
  const [bar, setBar] = useState('1H')
  const [days, setDays] = useState(180)
  const [symbols, setSymbols] = useState<string[]>(['BTC-USDT-SWAP'])
  const [instruments, setInstruments] = useState<string[]>(['BTC-USDT-SWAP','ETH-USDT-SWAP','SOL-USDT-SWAP'])
  const wsRef = useRef<WebSocket | null>(null)
  const { refreshGroups } = useStore()

  useEffect(() => { api.listStrategies().then((r) => setStrategies(r.strategies)) }, [])
  useEffect(() => { api.instruments().then((r) => setInstruments(r.instruments)).catch(() => {}) }, [])
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

  function buildSpec(): NodeSpec {
    const cs: ChildRefSpec[] = children.map((c) => ({ node: c.node, weight: c.weight, invert: c.invert }))
    return groupType === 'signal_combiner'
      ? { node_type: 'signal_combiner', name: groupName || 'combo', mode, children: cs, invert: false }
      : { node_type: 'allocation_group', name: groupName || 'group', children: cs, invert: false }
  }

  // WS 实时预览（debounce）
  useEffect(() => {
    const ws = wsRef.current
    if (!ws || ws.readyState !== WebSocket.OPEN || children.length === 0 || symbols.length === 0) return
    const t = setTimeout(() => {
      ws.send(JSON.stringify({ node_spec: buildSpec(), symbols, bar, days, initial_capital: 10000 }))
    }, 350)
    return () => clearTimeout(t)
  }, [children, groupType, mode, bar, days, symbols])

  function addFromStrategy(s: StrategyInstance) {
    const node: NodeSpec = { node_type: 'leaf', name: s.name, template_name: s.template_name,
                             strategy_kind: s.strategy_kind, params: s.params, invert: s.invert }
    setChildren((c) => [...c, { _id: uid(), node, weight: 1, invert: s.invert }])
    // 首个子策略带入其保存的 bar/days/symbols（若有），避免每次都要手动重设
    if (children.length === 0) {
      if (s.bar) setBar(s.bar)
      if (s.days) setDays(s.days)
      if (s.symbols && s.symbols.length) setSymbols(s.symbols)
    }
  }

  function onDragEnd(e: DragEndEvent) {
    const { active, over } = e
    if (!over) return
    const aType = active.data.current?.type
    const oType = over.data.current?.type
    if (aType === 'lib' && oType === 'canvas') {
      const s = strategies.find((x) => x.id === active.data.current?.sid)
      if (s) addFromStrategy(s)
      return
    }
    if (aType === 'node' && oType === 'node' && active.id !== over.id) {
      setChildren((c) => {
        const oldI = c.findIndex((x) => x._id === active.id)
        const newI = c.findIndex((x) => x._id === over.id)
        return arrayMove(c, oldI, newI)
      })
    }
  }

  async function save() {
    if (!groupName || children.length === 0) return
    try {
      await api.createGroup({ name: groupName, spec: buildSpec() })
      await refreshGroups()
      setMsg(`✓ 已保存策略组「${groupName}」`)
      setGroupName('')
    } catch (e) { setMsg((e as Error).message) }
  }

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }))
  const totalW = children.reduce((s, c) => s + c.weight, 0) || 1
  const childIds = children.map((c) => c._id)

  return (
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
      <div className="flex h-full">
        {/* 左：单策略库 */}
        <div className="w-64 shrink-0 border-r border-line p-4 overflow-auto">
          <div className="text-sm font-semibold mb-1">单策略库</div>
          <div className="text-xs text-dim mb-3">拖拽或点 + 添加到组合</div>
          <div className="space-y-2">
            {strategies.length === 0 && <div className="text-xs text-dim">先在「策略探索」保存单策略</div>}
            {strategies.map((s) => <LibItem key={s.id} s={s} onAdd={() => addFromStrategy(s)} />)}
          </div>
        </div>

        {/* 中：组合画布 */}
        <div className="flex-1 p-4 overflow-auto flex flex-col">
          <div className="flex items-center gap-3 mb-4">
            <div className="flex gap-1 p-1 bg-black/20 rounded-sm">
              {(['allocation_group', 'signal_combiner'] as const).map((t) => (
                <button key={t} onClick={() => setGroupType(t)}
                  className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${groupType === t ? 'bg-card-strong text-accent' : 'text-dim'}`}>
                  {t === 'allocation_group' ? '💼 资金分配' : '🔗 信号组合'}
                </button>
              ))}
            </div>
            {groupType === 'signal_combiner' && (
              <Select value={mode} onChange={setMode}
                options={['vote', 'majority', 'and', 'or', 'weighted'].map((m) => ({ value: m, label: m }))} />
            )}
          </div>

          <ComposeCanvas childIds={childIds}>
            {children.map((c) => (
              <NodeCard key={c._id} child={c} pct={(c.weight / totalW) * 100}
                onChange={(p) => setChildren((cs) => cs.map((x) => x._id === c._id ? { ...x, ...p } : x))}
                onRemove={() => setChildren((cs) => cs.filter((x) => x._id !== c._id))} />
            ))}
          </ComposeCanvas>

          <div className="flex items-center gap-2 mt-4">
            <Input value={groupName} onChange={(e) => setGroupName(e.target.value)} placeholder="策略组命名…" className="flex-1" />
            <Button variant="primary" onClick={save} disabled={!groupName || children.length === 0}>
              <Save size={15} className="inline mr-1.5" />保存策略组
            </Button>
          </div>
          {msg && <div className="text-xs text-accent mt-2 break-all">{msg}</div>}
        </div>

        {/* 右：组合回测预览 */}
        <div className="w-96 shrink-0 border-l border-line p-4 overflow-auto">
          <Card className="mb-4">
            <CardHeader title="回测参数" subtitle="预览用的行情上下文" />
            <div className="px-4 pb-4 space-y-3">
              <Field label="品种（单币 1 个；多币策略可选多个作 universe）">
                <MultiSymbolPicker value={symbols} onChange={setSymbols} instruments={instruments} min={1} />
              </Field>
              <div className="grid grid-cols-2 gap-2">
                <Field label="周期">
                  <Select value={bar} onChange={setBar} options={['1H','4H','1D'].map((b) => ({ value: b, label: b }))} className="w-full" />
                </Field>
                <Field label="回测天数">
                  <Input type="number" value={days} onChange={(e) => setDays(+e.target.value)} className="w-full" />
                </Field>
              </div>
            </div>
          </Card>
          <Card>
            <CardHeader title="组合回测预览"
              subtitle={`${symbols.join(', ')} · ${bar} · ${days}天`} />
            <div className="px-4 pb-4"><EquityChart equity={equity} benchmark={benchmark} /></div>
          </Card>
          <div className="mt-4"><MetricsGrid m={metrics} /></div>
        </div>
      </div>
    </DndContext>
  )
}

function ComposeCanvas({ childIds, children }: { childIds: string[]; children: React.ReactNode }) {
  const { setNodeRef, isOver } = useDroppable({ id: 'canvas', data: { type: 'canvas' } })
  return (
    <div ref={setNodeRef}
      className={`flex-1 rounded border border-dashed p-4 overflow-auto transition-colors ${isOver ? 'border-accent bg-accent/5' : 'border-line bg-black/10'}`}>
      <SortableContext items={childIds} strategy={verticalListSortingStrategy}>
        <div className="space-y-2 max-w-2xl mx-auto">
          {Array.isArray(children) && children.length === 0 && (
            <div className="text-dim text-sm text-center py-12">从左侧拖入单策略开始组合</div>
          )}
          {children}
        </div>
      </SortableContext>
    </div>
  )
}

function LibItem({ s, onAdd }: { s: StrategyInstance; onAdd: () => void }) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id: `lib_${s.id}`, data: { type: 'lib', sid: s.id } })
  return (
    <div ref={setNodeRef} {...attributes}
      className={`flex items-center gap-2 px-3 py-2 rounded bg-card border border-line hover:border-accent/30 cursor-grab ${isDragging ? 'opacity-40' : ''}`}>
      <button {...listeners} aria-label="拖拽到组合" className="text-dim"><GripVertical size={14} /></button>
      <div className="flex-1 min-w-0">
        <div className="text-sm truncate">{s.name}</div>
        <div className="text-[0.7rem] text-dim">{s.template_name}{s.strategy_kind === 'multi' ? ' · 多币' : ''}</div>
      </div>
      <button onClick={onAdd} aria-label="添加到组合" className="text-dim hover:text-accent"><Plus size={15} /></button>
    </div>
  )
}

function NodeCard({ child, pct, onChange, onRemove }: {
  child: EditChild; pct: number; onChange: (p: Partial<EditChild>) => void; onRemove: () => void
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: child._id, data: { type: 'node' } })
  const style = { transform: CSS.Transform.toString(transform), transition }
  const name = child.node.name || child.node.template_name || '?'
  return (
    <div ref={setNodeRef} style={style}
      className={`flex items-center gap-3 p-3 rounded bg-card border border-line ${isDragging ? 'border-accent shadow-accent' : ''}`}>
      <button {...attributes} {...listeners} className="text-dim cursor-grab"><GripVertical size={16} /></button>
      <div className="w-32 shrink-0">
        <div className="text-sm font-medium truncate">{name}</div>
        <div className="text-[0.7rem] text-dim">{child.node.template_name}</div>
      </div>
      <div className="flex-1 flex items-center gap-2">
        <span className="text-xs text-dim w-10 tnum">{pct.toFixed(0)}%</span>
        <Slider value={child.weight} min={0} max={5} step={0.1} onChange={(v) => onChange({ weight: v })} className="flex-1" />
      </div>
      <Toggle checked={child.invert} onChange={(v) => onChange({ invert: v })} label="反向" />
      <button onClick={onRemove} className="text-dim hover:text-down"><Trash2 size={15} /></button>
    </div>
  )
}
