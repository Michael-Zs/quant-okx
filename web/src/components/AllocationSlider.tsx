import { useRef, useState } from 'react'
import type { PointerEvent } from 'react'
import { cn } from '../lib/utils'

// 段配色（循环）
const SEG_COLORS = ['bg-accent', 'bg-up', 'bg-warn', 'bg-accent-2', 'bg-fuchsia-500', 'bg-orange-500']

/** 多手柄分段滑动条：把 100% 分给 N 个条目，拖动段边界（手柄）重新分配相邻两段占比。
 *
 * weights 为归一化占比（Σ≈1）。手柄 i（0..N-2）位于累积位置 cum[i]，
 * 拖到 x 时 weights[i] = x - cum[i-1]、weights[i+1] = cum[i+1] - x，其余段不变，Σ 保持 1。
 */
export function AllocationSlider({ items, weights, onChange, disabled }: {
  items: { id: string; label: string }[]
  weights: number[]
  onChange: (weights: number[]) => void
  disabled?: boolean
}) {
  const trackRef = useRef<HTMLDivElement>(null)
  const [dragIdx, setDragIdx] = useState<number | null>(null)
  const N = items.length

  // 累积边界 cum[i] = Σ(weights[0..i])
  const cum: number[] = []
  let acc = 0
  for (const w of weights) { acc += w; cum.push(acc) }

  function clientToFrac(clientX: number): number {
    if (!trackRef.current) return 0
    const rect = trackRef.current.getBoundingClientRect()
    return Math.max(0, Math.min(1, (clientX - rect.left) / rect.width))
  }

  function onHandleDown(i: number, e: PointerEvent) {
    if (disabled) return
    e.preventDefault()
    setDragIdx(i)
    ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
  }
  function onHandleMove(e: PointerEvent) {
    if (dragIdx === null) return
    const MIN = 0.05 // 最小段 5%，避免段消失
    const lo = dragIdx === 0 ? 0 : cum[dragIdx - 1]
    const hi = dragIdx >= N - 1 ? 1 : cum[dragIdx + 1]
    const x = Math.max(lo + MIN, Math.min(hi - MIN, clientToFrac(e.clientX)))
    const next = [...weights]
    next[dragIdx] = x - lo
    next[dragIdx + 1] = hi - x
    onChange(next)
  }
  function onHandleUp() { setDragIdx(null) }

  if (N === 0) return null

  return (
    <div className="select-none">
      <div ref={trackRef} className="relative flex h-10 rounded overflow-hidden border border-line bg-black/30">
        {items.map((it, i) => (
          <div key={it.id}
               className={cn('relative flex items-center justify-center overflow-hidden transition-[flex] ', SEG_COLORS[i % SEG_COLORS.length])}
               style={{ width: `${(weights[i] * 100).toFixed(2)}%` }}>
            <span className="text-[0.7rem] font-semibold text-black/75 tnum">{(weights[i] * 100).toFixed(0)}%</span>
          </div>
        ))}
        {/* 段边界手柄（拖动重分配相邻两段） */}
        {N > 1 && weights.slice(0, -1).map((_, i) => (
          <div key={`h${i}`} role="slider" aria-label={`${items[i]?.label}/${items[i + 1]?.label} 边界`}
               onPointerDown={(e) => onHandleDown(i, e)} onPointerMove={onHandleMove} onPointerUp={onHandleUp}
               className="absolute top-0 h-full w-4 -ml-2 cursor-ew-resize bg-bg2/95 border-x border-black/40 hover:bg-white touch-none flex items-center justify-center z-10"
               style={{ left: `${(cum[i] * 100).toFixed(2)}%` }}>
            <span className="text-[0.6rem] text-dim leading-none">‖</span>
          </div>
        ))}
      </div>
      {/* 标签 */}
      <div className="flex mt-1.5">
        {items.map((it, i) => (
          <div key={it.id} className="truncate px-1" style={{ width: `${(weights[i] * 100).toFixed(2)}%` }}>
            <span className={cn('inline-block w-2 h-2 rounded-sm mr-1 align-middle', SEG_COLORS[i % SEG_COLORS.length])} />
            <span className="text-[0.7rem] text-dim align-middle">{it.label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
