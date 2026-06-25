import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Activity, Bot, Boxes, Rocket, TrendingUp, Cpu, Database } from 'lucide-react'
import { api } from '../api/client'
import type { TemplateInfo, ConfigInfo, Deployment } from '../api/types'
import { MetricCard, Card, CardHeader, Badge } from '../components/ui'
import { useStore } from '../store/useStore'

export default function Dashboard() {
  const [templates, setTemplates] = useState<TemplateInfo[]>([])
  const [cfg, setCfg] = useState<ConfigInfo | null>(null)
  const [deps, setDeps] = useState<Deployment[]>([])
  const { strategies, groups, refreshStrategies, refreshGroups } = useStore()

  useEffect(() => {
    api.templates().then((r) => setTemplates(r.templates)).catch(() => {})
    api.config().then(setCfg).catch(() => {})
    api.listDeployments().then((r) => setDeps(r.deployments)).catch(() => {})
    refreshStrategies()
    refreshGroups()
  }, [refreshStrategies, refreshGroups])

  const multiCount = templates.filter((t) => t.strategy_kind === 'multi').length
  const singleCount = templates.length - multiCount
  const running = deps.filter((d) => d.alive).length

  const quickLinks = [
    { to: '/explore', icon: TrendingUp, label: '策略探索', desc: '模板调参 · 实时回测预览' },
    { to: '/compose', icon: Boxes, label: '策略组合', desc: '拖拽编排 · 信号/资金层' },
    { to: '/lab', icon: Bot, label: '策略实验室', desc: '写策略代码 · 参数网格搜索' },
    { to: '/multi', icon: Activity, label: '多币策略', desc: '跨币择优 · 持仓热力图' },
    { to: '/deploy', icon: Rocket, label: '实盘部署', desc: '策略组部署 · 监控' },
  ]

  return (
    <div className="p-4 md:p-6 max-w-6xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">仪表盘</h1>
        <p className="text-sm text-dim mt-1">OKX 量化交易控制台 · 总览</p>
      </div>

      {/* KPI */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <MetricCard label="策略模板" value={templates.length} sub={`${singleCount} 单币 / ${multiCount} 多币`} />
        <MetricCard label="已保存实例" value={strategies.length} sub={`${groups.length} 个策略组`} />
        <MetricCard label="运行中部署" value={running} tone={running > 0 ? 'up' : undefined} sub={`${deps.length} 个总部署`} />
        <MetricCard label="缓存文件" value={cfg?.cache.count ?? '—'} sub={cfg ? `${(cfg.cache.size_bytes / 1024 / 1024).toFixed(1)} MB` : ''} />
      </div>

      {/* 服务状态 */}
      <Card className="mb-6">
        <CardHeader title="服务状态" />
        <div className="px-4 pb-4 grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
          <div className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${cfg ? 'bg-up' : 'bg-down'}`} />
            <span className="text-dim">REST API</span>
            <span className="text-text">{cfg ? `127.0.0.1:${cfg.api_port}` : '离线'}</span>
          </div>
          <div className="flex items-center gap-2">
            <Cpu size={14} className="text-dim" />
            <span className="text-dim">OKX 凭证</span>
            {cfg?.okx_configured ? <Badge color="up">已配置</Badge> : <Badge color="down">未配置</Badge>}
          </div>
          <div className="flex items-center gap-2">
            <Database size={14} className="text-dim" />
            <span className="text-dim">API Token</span>
            {cfg?.api_token_set ? <Badge color="up">已设置</Badge> : <Badge color="warn">默认值</Badge>}
          </div>
        </div>
      </Card>

      {/* 快捷入口 */}
      <h2 className="text-sm font-semibold text-dim uppercase tracking-wider mb-3">快捷入口</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 mb-6">
        {quickLinks.map(({ to, icon: Icon, label, desc }) => (
          <Link key={to} to={to}
            className="block p-4 rounded border border-line bg-card hover:bg-card-strong hover:border-accent/35 transition-all">
            <div className="flex items-center gap-2 mb-1">
              <Icon size={16} className="text-accent" />
              <span className="font-medium text-sm">{label}</span>
            </div>
            <div className="text-xs text-dim">{desc}</div>
          </Link>
        ))}
      </div>

      {/* 策略模板列表 */}
      <Card>
        <CardHeader title="已注册策略模板" subtitle={`${templates.length} 个（用户保存的代码 .py 会即时注册）`} />
        <div className="px-4 pb-4 space-y-1.5 max-h-72 overflow-auto">
          {templates.length === 0 ? (
            <div className="text-dim text-sm py-4 text-center">加载中…</div>
          ) : templates.map((t) => (
            <div key={t.name} className="flex items-start justify-between py-1.5 border-b border-line/50 last:border-0">
              <div className="min-w-0">
                <div className="text-sm font-medium flex items-center gap-2">
                  {t.display_name}
                  <Badge color={t.strategy_kind === 'multi' ? 'accent-2' : 'dim'}>
                    {t.strategy_kind === 'multi' ? '多币' : '单币'}
                  </Badge>
                </div>
                <div className="text-xs text-dim mt-0.5 line-clamp-1">{t.description}</div>
              </div>
              <code className="text-[0.7rem] text-dim/70 shrink-0 ml-2">{t.name}</code>
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}
