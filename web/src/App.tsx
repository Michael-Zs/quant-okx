import { useState } from 'react'
import { Routes, Route, NavLink } from 'react-router-dom'
import { FlaskConical, Layers, Rocket } from 'lucide-react'
import { cn } from './lib/utils'
import Explore from './pages/Explore'
import Compose from './pages/Compose'
import Deploy from './pages/Deploy'

const nav = [
  { to: '/explore', label: '策略探索', icon: FlaskConical, desc: '模板调参 · 保存单策略' },
  { to: '/compose', label: '策略组合', icon: Layers, desc: '拖拽编排 · 占比 · 反向' },
  { to: '/deploy', label: '实盘部署', icon: Rocket, desc: '策略组 · 多组占比 · 监控' },
]

export default function App() {
  return (
    <div className="min-h-screen flex">
      <aside className="w-60 shrink-0 border-r border-line bg-black/20 p-4 flex flex-col gap-1">
        <div className="px-1 py-3 mb-2">
          <div className="text-lg font-bold tracking-tight">量化控制台</div>
          <div className="text-xs text-dim mt-0.5">OKX · 模块化策略</div>
        </div>
        {nav.map(({ to, label, icon: Icon, desc }) => (
          <NavLink key={to} to={to} className={({ isActive }) =>
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
          <Route path="/" element={<Explore />} />
          <Route path="/explore" element={<Explore />} />
          <Route path="/compose" element={<Compose />} />
          <Route path="/deploy" element={<Deploy />} />
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
