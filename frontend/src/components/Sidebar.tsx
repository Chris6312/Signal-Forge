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
  TerminalSquare,
} from 'lucide-react'
import clsx from 'clsx'
import MarketStatusBadge from './MarketStatusBadge'

const navItems = [
  { to: '/dashboard', label: 'Command Center', icon: LayoutDashboard },
  { to: '/watchlist', label: 'Radar Array', icon: ListChecks },
  { to: '/monitoring', label: 'Live Telemetry', icon: Activity },
  { to: '/positions', label: 'Active Vectors', icon: TrendingUp },
  { to: '/ledger', label: 'Paper Ledger', icon: BookOpen },
  { to: '/trades', label: 'Execution Log', icon: Clock },
  { to: '/audit', label: 'System Audit', icon: FileText },
  { to: '/runtime', label: 'Engine Config', icon: Settings },
]

export default function Sidebar() {
  return (
    <aside className="w-64 shrink-0 flex flex-col bg-[#0b0c13] border-r border-surface-border min-h-screen relative z-10">
      {/* Brand Header with Live Pulse */}
      <div className="flex items-center justify-between px-6 py-6 border-b border-surface-border">
        <div className="flex items-center gap-3">
          <TerminalSquare size={22} className="text-brand" />
          <span className="font-bold text-white tracking-widest uppercase text-sm">Forge_OS</span>
        </div>
        <div className="relative flex h-2.5 w-2.5">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-system-online opacity-75"></span>
          <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-system-online"></span>
        </div>
      </div>

      <nav className="flex-1 px-3 py-6 flex flex-col gap-1.5">
        <div className="px-3 mb-2 text-[10px] text-gray-500 font-mono tracking-widest uppercase">System Modules</div>
        {navItems.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              clsx(
                'flex items-center gap-3 px-3 py-2.5 rounded-md text-sm transition-all duration-200 group',
                isActive
                  ? 'bg-brand/10 text-brand border-l-2 border-brand font-medium'
                  : 'text-gray-400 border-l-2 border-transparent hover:text-white hover:bg-surface-hover hover:border-gray-600',
              )
            }
          >
            <Icon size={16} className="opacity-80 group-hover:opacity-100" />
            <span className="tracking-wide">{label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="px-6 py-4">
        <MarketStatusBadge />
      </div>

      <div className="px-6 py-4 border-t border-surface-border bg-surface-card/50 flex justify-between items-center text-xs mono">
        <span className="text-gray-600">SYS_VER</span>
        <span className="text-brand">v1.0.0</span>
      </div>
    </aside>
  )
}