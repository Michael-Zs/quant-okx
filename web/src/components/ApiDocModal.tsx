import { useEffect, useState } from 'react'
import { Terminal, X, Copy, Download } from 'lucide-react'
import { api } from '../api/client'

/** REST API 使用规范弹窗：拉取后端 api_spec 文本，供 Agent / 外部脚本复制。 */
export function ApiDocModal({ onClose }: { onClose: () => void }) {
  const [data, setData] = useState<{ spec: string; filename: string } | null>(null)
  const [err, setErr] = useState('')
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    api.apiSpec().then((r) => setData({ spec: r.spec, filename: r.filename })).catch((e) => setErr(String(e)))
  }, [])

  async function copy() {
    if (!data) return
    try {
      await navigator.clipboard.writeText(data.spec)
      setCopied(true); setTimeout(() => setCopied(false), 2000)
    } catch { setErr('自动复制受限，请手动选中下方文本复制') }
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
      <div className="w-[min(960px,94vw)] h-[88vh] bg-card-strong border border-line rounded-md flex flex-col"
           onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-line">
          <div className="flex items-center gap-2">
            <Terminal size={16} className="text-accent" />
            <div className="text-sm font-semibold">REST API 使用规范（供 Agent / 外部脚本）</div>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={copy} disabled={!data}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs bg-accent/15 text-accent hover:bg-accent/25 disabled:opacity-50">
              <Copy size={13} /> {copied ? '已复制' : '复制'}
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
          复制这份规范给 AI（Claude / ChatGPT 等）或外部脚本，它就能调本控制台的 REST API 做回测、部署、监控。Base URL：http://127.0.0.1:8787
        </div>
      </div>
    </div>
  )
}
