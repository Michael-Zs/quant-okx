import { useState } from 'react'
import { Routes, Route, NavLink } from 'react-router-dom'
import { LayoutDashboard, FlaskConical, Layers, Rocket, Bot, Activity, Settings as Cog } from 'lucide-react'
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
  return (
    <div className="min-h-screen flex">
      <aside className="w-60 shrink-0 border-r border-line bg-black/20 p-4 flex flex-col gap-1 overflow-y-auto">
        <div className="px-1 py-3 mb-2">
          <div className="text-lg font-bold tracking-tight">量化控制台</div>
          <div className="text-xs text-dim mt-0.5">OKX · 模块化策略</div>
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
      <main className="flex-1 overflow-auto">
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
