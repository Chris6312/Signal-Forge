import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  ListChecks,
  Activity,
  TrendingUp,
  BookOpen,
  Clock,
  FileText,
  Settings,
  Zap,
} from 'lucide-react'
import clsx from 'clsx'
import MarketStatusBadge from './MarketStatusBadge'

const navItems = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/watchlist', label: 'Watchlist', icon: ListChecks },
  { to: '/monitoring', label: 'Monitoring', icon: Activity },
  { to: '/positions', label: 'Positions', icon: TrendingUp },
  { to: '/ledger', label: 'Paper Ledger', icon: BookOpen },
  { to: '/trades', label: 'Trade History', icon: Clock },
  { to: '/audit', label: 'Audit Trail', icon: FileText },
  { to: '/runtime', label: 'Runtime & Risk', icon: Settings },
]

export default function Sidebar() {
  return (
    <aside className="w-56 shrink-0 flex flex-col bg-surface-card border-r border-surface-border min-h-screen">
      <div className="flex items-center gap-2 px-5 py-5 border-b border-surface-border">
        <Zap size={20} className="text-brand" />
        <span className="font-bold text-white tracking-tight">Signal Forge</span>
      </div>

      <nav className="flex-1 px-3 py-4 flex flex-col gap-1">
        {navItems.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              clsx(
                'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors',
                isActive
                  ? 'bg-brand/20 text-brand font-medium'
                  : 'text-gray-400 hover:text-white hover:bg-surface-hover',
              )
            }
          >
            <Icon size={16} />
            {label}
          </NavLink>
        ))}
      </nav>

      <MarketStatusBadge />

      <div className="px-5 py-4 border-t border-surface-border text-xs text-gray-600 mono">
        v1.0.0
      </div>
    </aside>
  )
}
