import { useEffect, useState } from 'react'
import { Bot, X, Copy, Download } from 'lucide-react'
import { api } from '../api/client'

/** AI 策略开发规范弹窗：拉取后端 spec 文本，支持复制 / 下载 .md。 */
export function SpecModal({ kind, onClose }: { kind: 'single' | 'multi'; onClose: () => void }) {
  const [data, setData] = useState<{ spec: string; filename: string } | null>(null)
  const [err, setErr] = useState('')
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    api.strategySpec(kind).then((r) => setData({ spec: r.spec, filename: r.filename })).catch((e) => setErr(String(e)))
  }, [kind])

  function copyHint() {
    const hint = `Fetch the ${
      kind === 'single' ? 'single-asset (Strategy)' : 'multi-asset (MultiStrategy)'
    } development spec from:\nGET http://127.0.0.1:8787/api/strategy_spec?kind=${kind}\n\nFollow the spec and write a strategy.`
    navigator.clipboard.writeText(hint)
      .then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000) })
      .catch(() => setErr('复制失败，请手动复制'))
  }

  function download() {
    if (!data) return
    const url = URL.createObjectURL(new Blob([data.spec], { type: 'text/markdown' }))
    const a = document.createElement('a')
    a.href = url; a.download = data.filename; a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div className="w-[min(900px,92vw)] h-[85vh] bg-card-strong border border-line rounded-md flex flex-col"
           onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-line">
          <div className="flex items-center gap-2">
            <Bot size={16} className="text-accent" />
            <div className="text-sm font-semibold">AI 策略开发规范（{kind === 'single' ? '单币 Strategy' : '多币 MultiStrategy'}）</div>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={copyHint}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs bg-accent/15 text-accent hover:bg-accent/25">
              <Copy size={13} /> {copied ? '已复制' : '复制提示给 AI'}
            </button>
            <button onClick={download} disabled={!data}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs bg-card text-dim hover:text-text disabled:opacity-50 border border-line">
              <Download size={13} /> 下载 .md
            </button>
            <button onClick={onClose} className="p-1 rounded text-dim hover:text-text"><X size={16} /></button>
          </div>
        </div>
        <div className="flex-1 overflow-auto p-4 text-xs leading-relaxed text-dim">
          {err ? <div className="text-down">{err}</div>
            : !data ? <div>加载中…</div>
            : <pre className="whitespace-pre-wrap font-mono text-[0.7rem]">{data.spec}</pre>}
        </div>
        <div className="px-4 py-2 border-t border-line text-[0.7rem] text-dim/70">
          点击「复制提示给 AI」将获取规范的 API 调用指令发给 Agent，Agent 会自动拉取完整开发规范并按需编写策略代码。
        </div>
      </div>
    </div>
  )
}
