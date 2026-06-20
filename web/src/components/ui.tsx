import type { ReactNode, ButtonHTMLAttributes, InputHTMLAttributes } from 'react'
import { cn } from '../lib/utils'

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cn('rounded border border-line bg-card', className)}>{children}</div>
}

export function CardHeader({ title, subtitle, action }: { title: ReactNode; subtitle?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex items-start justify-between p-4 pb-2">
      <div>
        <div className="font-semibold tracking-tight">{title}</div>
        {subtitle && <div className="text-xs text-dim mt-0.5">{subtitle}</div>}
      </div>
      {action}
    </div>
  )
}

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'
export function Button({ variant = 'secondary', className, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  const styles: Record<Variant, string> = {
    primary: 'bg-gradient-to-br from-accent to-cyan-700 text-[#00121a] font-semibold shadow-accent hover:shadow-accent-hover',
    secondary: 'bg-card border border-line text-text hover:bg-card-strong',
    ghost: 'text-dim hover:text-text hover:bg-card',
    danger: 'bg-down/15 text-down border border-down/30 hover:bg-down/25',
  }
  return <button className={cn('px-3.5 py-2 rounded-sm text-sm transition-all disabled:opacity-40 disabled:cursor-not-allowed', styles[variant], className)} {...props} />
}

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label?: string }) {
  return (
    <button type="button" onClick={() => onChange(!checked)} className="flex items-center gap-2 group">
      <span className={cn('w-9 h-5 rounded-full p-0.5 transition-colors', checked ? 'bg-accent' : 'bg-white/10')}>
        <span className={cn('block w-4 h-4 rounded-full bg-white transition-transform', checked && 'translate-x-4')} />
      </span>
      {label && <span className="text-xs text-dim group-hover:text-text">{label}</span>}
    </button>
  )
}

export function Slider({ value, min, max, step, onChange, className }: { value: number; min: number; max: number; step: number; onChange: (v: number) => void; className?: string }) {
  return (
    <input type="range" value={value} min={min} max={max} step={step}
      onChange={(e) => onChange(parseFloat(e.target.value))} className={cn('w-full h-1.5 cursor-pointer', className)} />
  )
}

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn('px-3 py-2 rounded-sm bg-black/30 border border-line text-sm text-text placeholder:text-dim outline-none focus:border-accent transition-colors', className)} {...props} />
}

export function Select({ value, onChange, options, className }: { value: string; onChange: (v: string) => void; options: { value: string; label: string }[]; className?: string }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)}
      className={cn('px-3 py-2 rounded-sm bg-black/30 border border-line text-sm text-text outline-none focus:border-accent cursor-pointer', className)}>
      {options.map((o) => <option key={o.value} value={o.value} className="bg-bg2">{o.label}</option>)}
    </select>
  )
}

export function Badge({ children, color = 'accent' }: { children: ReactNode; color?: 'accent' | 'up' | 'down' | 'dim' | 'warn' | 'accent-2' }) {
  const colors = {
    accent: 'text-accent bg-accent/10', 'accent-2': 'text-accent-2 bg-accent-2/10',
    up: 'text-up bg-up/10', down: 'text-down bg-down/10', dim: 'text-dim bg-white/5', warn: 'text-warn bg-warn/10',
  }
  return <span className={cn('px-2 py-0.5 rounded text-xs font-medium', colors[color])}>{children}</span>
}

export function MetricCard({ label, value, sub, tone }: { label: string; value: ReactNode; sub?: ReactNode; tone?: 'up' | 'down' }) {
  return (
    <div className="rounded border border-line bg-card p-3.5 hover:border-accent/35 hover:bg-card-strong transition-colors">
      <div className="text-[0.7rem] uppercase tracking-wider text-dim">{label}</div>
      <div className={cn('text-xl font-semibold tnum mt-1', tone === 'up' && 'text-up', tone === 'down' && 'text-down')}>{value}</div>
      {sub && <div className="text-xs text-dim mt-0.5">{sub}</div>}
    </div>
  )
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block">
      <div className="text-xs text-dim mb-1.5">{label}</div>
      {children}
      {hint && <div className="text-[0.7rem] text-dim/70 mt-1">{hint}</div>}
    </label>
  )
}
