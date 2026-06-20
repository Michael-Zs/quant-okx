import { useState, useRef, useEffect, type Dispatch, type SetStateAction } from 'react'
import { ChevronDown, X } from 'lucide-react'
import { cn } from '../lib/utils'

/** 搜索下拉单选：输入过滤合约列表，点击选中。 */
export function SymbolPicker({ value, onChange, instruments, placeholder = '搜索品种…' }: {
  value: string
  onChange: (v: string) => void
  instruments: string[]
  placeholder?: string
}) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])
  const ql = q.toLowerCase()
  const filtered = instruments.filter((s) => s.toLowerCase().includes(ql)).slice(0, 150)
  return (
    <div ref={ref} className="relative">
      <button type="button" onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-3 py-2 rounded-sm bg-black/30 border border-line text-sm text-text outline-none focus:border-accent">
        <span className={value ? '' : 'text-dim'}>{value || placeholder}</span>
        <ChevronDown size={15} className={cn('text-dim transition-transform', open && 'rotate-180')} />
      </button>
      {open && (
        <div className="absolute z-30 mt-1 w-full rounded-sm border border-line bg-bg2 shadow-lg">
          <div className="p-2 border-b border-line">
            <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="输入过滤（如 BTC）…"
              className="w-full px-2 py-1.5 rounded-sm bg-black/40 border border-line text-sm outline-none focus:border-accent" />
          </div>
          <div className="max-h-60 overflow-auto">
            {filtered.map((s) => (
              <button key={s} type="button"
                onClick={() => { onChange(s); setOpen(false); setQ('') }}
                className={cn('w-full text-left px-3 py-1.5 text-sm hover:bg-card', s === value && 'text-accent')}>
                {s}
              </button>
            ))}
            {filtered.length === 0 && <div className="px-3 py-3 text-xs text-dim">无匹配</div>}
          </div>
        </div>
      )}
    </div>
  )
}

/** 搜索多选：输入过滤→选中加入标签，标签可删。用于多币 universe / 部署 symbols。 */
export function MultiSymbolPicker({ value, onChange, instruments, placeholder = '搜索添加品种…', min = 1 }: {
  value: string[]
  onChange: Dispatch<SetStateAction<string[]>>
  instruments: string[]
  placeholder?: string
  min?: number
}) {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])
  const ql = q.toLowerCase()
  const filtered = instruments.filter((s) => s.toLowerCase().includes(ql) && !value.includes(s)).slice(0, 150)
  // 函数式更新：连续快速 add/remove 时 prev 始终为最新 state，避免闭包 stale 挤掉前一项
  function add(s: string) { onChange((prev) => prev.includes(s) ? prev : [...prev, s]); setQ('') }
  function remove(s: string) { onChange((prev) => prev.length > min ? prev.filter((x) => x !== s) : prev) }
  return (
    <div ref={ref} className="relative">
      <div className="flex flex-wrap gap-1.5 p-2 rounded-sm bg-black/30 border border-line min-h-[42px] cursor-text">
        {value.map((s) => (
          <span key={s} className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-accent/10 text-accent text-xs">
            {s}
            <button type="button" onClick={(e) => { e.stopPropagation(); remove(s) }}
              className="hover:text-down"><X size={11} /></button>
          </span>
        ))}
        <input value={q} onChange={(e) => { setQ(e.target.value); setOpen(true) }}
          onFocus={() => setOpen(true)}
          placeholder={value.length === 0 ? placeholder : '+ 添加品种'}
          className="flex-1 min-w-[100px] bg-transparent text-sm outline-none placeholder:text-dim" />
      </div>
      {open && filtered.length > 0 && (
        <div className="absolute z-30 mt-1 w-full rounded-sm border border-line bg-bg2 shadow-lg max-h-60 overflow-auto">
          {filtered.map((s) => (
            <button key={s} type="button" onClick={() => add(s)}
              className="w-full text-left px-3 py-1.5 text-sm hover:bg-card">{s}</button>
          ))}
        </div>
      )}
    </div>
  )
}
