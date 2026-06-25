import { useEffect, useState } from 'react'
import { Routes, Route, NavLink, useLocation } from 'react-router-dom'
import { LayoutDashboard, FlaskConical, Layers, Rocket, Bot, Activity, Settings as Cog, Menu, X } from 'lucide-react'
import { cn } from './lib/utils'
import Dashboard from './pages/Dashboard'
import Explore from './pages/Explore'
import Compose from './pages/Compose'
import Multi from './pages/Multi'
import Lab from './pages/Lab'
import Deploy from './pages/Deploy'
import Settings from './pages/Settings'

const nav = [
  { to: '/', label: '仪表盘', icon: LayoutDashboard, desc: '总览 · 状态 · 快捷入口', end: true },
  { to: '/explore', label: '策略探索', icon: FlaskConical, desc: '模板调参 · 实时回测' },
  { to: '/compose', label: '策略组合', icon: Layers, desc: '拖拽编排 · 占比 · 反向' },
  { to: '/multi', label: '多币策略', icon: Activity, desc: '跨币择优 · 持仓热力图' },
  { to: '/lab', label: '策略实验室', icon: Bot, desc: '写策略代码 · 网格搜索' },
  { to: '/deploy', label: '实盘部署', icon: Rocket, desc: '策略组 · 多组占比 · 监控' },
  { to: '/settings', label: '设置', icon: Cog, desc: 'API key · 默认参数 · 缓存' },
]

export default function App() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const location = useLocation()

  // 路由切换时关闭移动端抽屉
  useEffect(() => { setSidebarOpen(false) }, [location.pathname])

  // 抽屉打开时锁定 body 滚动，关闭/卸载时还原
  useEffect(() => {
    if (!sidebarOpen) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = prev }
  }, [sidebarOpen])

  return (
    <div className="min-h-screen md:flex">
      {/* 移动端顶栏（桌面隐藏） */}
      <header className="md:hidden sticky top-0 z-30 flex items-center gap-3 px-4 h-12 border-b border-line bg-bg/90 backdrop-blur">
        <button onClick={() => setSidebarOpen(true)} aria-label="打开菜单" className="p-1.5 -ml-1.5 text-text hover:text-accent">
          <Menu size={20} />
        </button>
        <div className="text-sm font-semibold tracking-tight">量化控制台</div>
      </header>

      {/* 移动端遮罩（仅抽屉打开时） */}
      {sidebarOpen && (
        <div onClick={() => setSidebarOpen(false)} className="md:hidden fixed inset-0 z-40 bg-black/60 backdrop-blur-sm" />
      )}

      {/* 侧边栏：桌面常驻 w-60 / 移动 fixed 抽屉 */}
      <aside className={cn(
        'border-line bg-black/20 p-4 flex flex-col gap-1 overflow-y-auto',
        // 桌面：常驻、占文档流
        'md:w-60 md:shrink-0 md:static md:translate-x-0 md:border-r',
        // 移动：fixed 抽屉，默认移出视口
        'fixed inset-y-0 left-0 z-50 w-72 max-w-[80vw] border-r transition-transform duration-200 ease-out',
        sidebarOpen ? 'translate-x-0' : '-translate-x-full',
      )}>
        <div className="px-1 py-3 mb-2 flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="text-lg font-bold tracking-tight">量化控制台</div>
            <div className="text-xs text-dim mt-0.5">OKX · 模块化策略</div>
          </div>
          <button onClick={() => setSidebarOpen(false)} aria-label="关闭菜单" className="md:hidden text-dim hover:text-text shrink-0">
            <X size={18} />
          </button>
        </div>
        {nav.map(({ to, label, icon: Icon, desc, end }) => (
          <NavLink key={to} to={to} end={end} className={({ isActive }) =>
            cn('block px-3 py-2.5 rounded-sm transition-colors',
               isActive ? 'bg-card-strong text-accent' : 'text-dim hover:text-text hover:bg-card')}>
            <div className="flex items-center gap-2.5 text-sm font-medium">
              <Icon size={17} /> {label}
            </div>
            <div className="text-[0.7rem] text-dim/70 mt-0.5 ml-7">{desc}</div>
          </NavLink>
        ))}
        <div className="mt-auto pt-4 border-t border-line">
          <TokenSetting />
        </div>
      </aside>

      {/* 主内容区：移动端随 body 自然滚动；桌面端独立滚动 */}
      <main className="flex-1 md:h-screen md:overflow-auto">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/explore" element={<Explore />} />
          <Route path="/compose" element={<Compose />} />
          <Route path="/multi" element={<Multi />} />
          <Route path="/lab" element={<Lab />} />
          <Route path="/deploy" element={<Deploy />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  )
}

function TokenSetting() {
  const [v, setV] = useState(localStorage.getItem('api_token') || '')
  const [saved, setSaved] = useState(false)
  return (
    <div>
      <div className="text-[0.7rem] uppercase tracking-wider text-dim mb-1.5">API Token</div>
      <input
        value={v}
        onChange={(e) => { setV(e.target.value); setSaved(false) }}
        onBlur={() => { localStorage.setItem('api_token', v); setSaved(true) }}
        placeholder="change_me（写操作需鉴权）"
        className="w-full px-2 py-1.5 rounded-sm bg-black/30 border border-line text-xs text-text outline-none focus:border-accent"
        type="password"
      />
      {saved && <div className="text-[0.65rem] text-up mt-1">✓ 已保存</div>}
    </div>
  )
}
