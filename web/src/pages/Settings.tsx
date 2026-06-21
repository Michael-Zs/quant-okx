import { useEffect, useState } from 'react'
import { Settings as Cog, Save, Trash2, RefreshCw, KeyRound, Database, Server, Terminal } from 'lucide-react'
import { api } from '../api/client'
import type { ConfigInfo } from '../api/types'
import { Card, CardHeader, Button, Input, Field, Badge } from '../components/ui'
import { ApiDocModal } from '../components/ApiDocModal'

export default function Settings() {
  const [cfg, setCfg] = useState<ConfigInfo | null>(null)
  const [k1, setK1] = useState(''); const [k2, setK2] = useState(''); const [k3, setK3] = useState('')
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)
  const [loading, setLoading] = useState(false)
  const [apiDocOpen, setApiDocOpen] = useState(false)

  async function refresh() {
    const c = await api.config(); setCfg(c)
  }
  useEffect(() => { refresh() }, [])

  async function saveEnv() {
    if (!k1 && !k2 && !k3) { setMsg({ kind: 'err', text: '请至少填写一项' }); return }
    try {
      const r = await api.updateEnv({ OKX_API_KEY: k1 || undefined, OKX_API_SECRET: k2 || undefined, OKX_API_PASSPHRASE: k3 || undefined })
      setMsg({ kind: 'ok', text: `已写入 .env：${r.updated.join(', ')}。${r.note}。` })
      setK1(''); setK2(''); setK3('')
      await refresh()
    } catch (e) { setMsg({ kind: 'err', text: (e as Error).message }) }
  }

  async function clearCache() {
    if (!confirm(`确定清空全部缓存（${cfg?.cache.count ?? 0} 个 parquet 文件）？下次拉数据需重新请求 OKX。`)) return
    setLoading(true)
    try {
      const r = await api.clearCache()
      setMsg({ kind: 'ok', text: `已清空 ${r.cleared} 个缓存文件` })
      await refresh()
    } catch (e) { setMsg({ kind: 'err', text: (e as Error).message }) }
    finally { setLoading(false) }
  }

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
          <Cog size={22} className="text-accent" /> 设置
        </h1>
        <p className="text-sm text-dim mt-1">OKX 凭证、REST API 信息、默认参数、缓存管理。</p>
      </div>

      {/* OKX 凭证 */}
      <Card className="mb-5">
        <CardHeader title={<span className="flex items-center gap-2"><KeyRound size={15} /> OKX API 密钥</span>}
          subtitle="存储于本地 .env（已 gitignore）。修改后需重启控制台 / API 生效。"
          action={cfg?.okx_configured ? <Badge color="up">已配置</Badge> : <Badge color="down">未配置</Badge>} />
        <div className="px-4 pb-4 space-y-3">
          <Field label="API Key"><Input type="password" value={k1} onChange={(e) => setK1(e.target.value)} placeholder="留空则不改" className="w-full" /></Field>
          <Field label="API Secret"><Input type="password" value={k2} onChange={(e) => setK2(e.target.value)} placeholder="留空则不改" className="w-full" /></Field>
          <Field label="Passphrase"><Input type="password" value={k3} onChange={(e) => setK3(e.target.value)} placeholder="留空则不改" className="w-full" /></Field>
          <Button variant="primary" onClick={saveEnv}><Save size={15} className="inline mr-1.5" />保存到 .env</Button>
        </div>
      </Card>

      {/* REST API 信息 */}
      <Card className="mb-5">
        <CardHeader title={<span className="flex items-center gap-2"><Server size={15} /> REST API</span>}
          subtitle="控制类接口（回测 / 启停实盘 / 查余额）需在请求头带 X-API-Token。"
          action={<Button variant="ghost" onClick={() => setApiDocOpen(true)}><Terminal size={14} className="inline mr-1" />API 规范</Button>} />
        <div className="px-4 pb-4 text-sm space-y-1.5 font-mono">
          <div><span className="text-dim">地址：</span><span className="text-text">{cfg ? `http://${cfg.api_host}:${cfg.api_port}` : '—'}</span></div>
          <div><span className="text-dim">文档：</span><span className="text-accent">{cfg ? `http://${cfg.api_host}:${cfg.api_port}/docs` : '—'}</span></div>
          <div className="flex items-center gap-2">
            <span className="text-dim">Token：</span>
            {cfg?.api_token_set ? <Badge color="up">已设置（非默认）</Badge> : <Badge color="warn">仍是默认值 change_me</Badge>}
          </div>
          <div className="text-[0.7rem] text-dim/70 mt-2 not-italic">
            点右上「API 规范」可复制一份 Agent / 外部脚本可直接使用的 REST API 使用说明（含全部端点 + curl/Python 示例 + 端到端工作流）。
          </div>
        </div>
      </Card>

      {/* 默认参数 */}
      <Card className="mb-5">
        <CardHeader title="默认交易参数（来自 .env）" />
        <div className="px-4 pb-4 grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
          {cfg ? (
            <>
              <ParamRow label="默认杠杆" v={String(cfg.defaults.leverage)} />
              <ParamRow label="仓位比例" v={cfg.defaults.position_ratio.toString()} />
              <ParamRow label="手续费率" v={cfg.defaults.fee.toString()} />
              <ParamRow label="滑点" v={cfg.defaults.slippage.toString()} />
            </>
          ) : <div className="text-dim col-span-4">加载中…</div>}
        </div>
      </Card>

      {/* 缓存 */}
      <Card className="mb-5">
        <CardHeader title={<span className="flex items-center gap-2"><Database size={15} /> 数据缓存</span>}
          subtitle="parquet K 线缓存，访问时自动增量更新。"
          action={<Button variant="ghost" onClick={refresh}><RefreshCw size={14} className="inline mr-1" />刷新</Button>} />
        <div className="px-4 pb-4">
          <div className="text-sm space-y-1 mb-3">
            <div><span className="text-dim">目录：</span><code className="text-text text-xs">{cfg?.cache.dir ?? '—'}</code></div>
            <div><span className="text-dim">文件数：</span><span className="text-text">{cfg?.cache.count ?? '—'}</span>
                  <span className="text-dim"> ｜ 大小：</span><span className="text-text">{cfg ? `${(cfg.cache.size_bytes / 1024 / 1024).toFixed(1)} MB` : '—'}</span></div>
            <div><span className="text-dim">策略目录：</span><code className="text-text text-xs">{cfg?.strategies_dir ?? '—'}</code></div>
          </div>
          <Button variant="danger" onClick={clearCache} disabled={loading || !cfg?.cache.count}>
            <Trash2 size={15} className="inline mr-1.5" />清空全部缓存
          </Button>
        </div>
      </Card>

      {msg && (
        <div className={`text-xs rounded px-3 py-2 sticky bottom-4 ${msg.kind === 'ok' ? 'text-up bg-up/10 border border-up/30' : 'text-down bg-down/10 border border-down/30'}`}>
          {msg.text}
        </div>
      )}

      {apiDocOpen && <ApiDocModal onClose={() => setApiDocOpen(false)} />}
    </div>
  )
}

function ParamRow({ label, v }: { label: string; v: string }) {
  return (
    <div className="rounded border border-line bg-card p-2.5">
      <div className="text-[0.7rem] uppercase tracking-wider text-dim">{label}</div>
      <div className="text-sm font-mono mt-0.5">{v}</div>
    </div>
  )
}
