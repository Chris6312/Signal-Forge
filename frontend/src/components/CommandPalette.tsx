import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Command } from 'cmdk'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  Terminal, LayoutDashboard, ListChecks, Activity, TrendingUp,
  BookOpen, Clock, FileText, Settings, RefreshCw
} from 'lucide-react'

export default function CommandPalette() {
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  // Toggle the menu when ⌘K or Ctrl+K is pressed
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === 'k' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault()
        setOpen((open) => !open)
      }
    }
    document.addEventListener('keydown', down)
    return () => document.removeEventListener('keydown', down)
  }, [])

  const runCommand = (command: () => void) => {
    setOpen(false)
    command()
  }

  const navigateTo = (path: string, label: string) => {
    runCommand(() => {
      navigate(path)
      toast.info('[SYS_NAV]', { description: `Rerouting to ${label}...` })
    })
  }

  const forceSync = () => {
    runCommand(() => {
      queryClient.invalidateQueries()
      toast.success('[SYS_SYNC]', { description: 'Manual uplink sync requested across all modules.' })
    })
  }

  return (
    <Command.Dialog
      open={open}
      onOpenChange={setOpen}
      label="Global Command Menu"
      className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-2xl bg-[#0b0c13] border border-surface-border rounded-xl shadow-[0_0_50px_-10px_rgba(99,102,241,0.25)] z-[200] overflow-hidden font-mono animate-in fade-in zoom-in-95 duration-200"
    >
      <div className="flex items-center px-4 border-b border-surface-border bg-surface-card/50">
        <Terminal size={18} className="text-brand mr-3 animate-pulse-slow" />
        <Command.Input
          className="w-full bg-transparent text-white py-4 text-sm focus:outline-none placeholder:text-gray-600"
          placeholder="Execute command or jump to module... (e.g. 'Dashboard', 'Sync')"
        />
        <div className="flex items-center gap-1 text-[10px] text-gray-500 bg-surface-border px-2 py-1 rounded">
          <span>ESC</span>
        </div>
      </div>

      <Command.List className="max-h-[350px] overflow-y-auto p-2 scrollbar-thin">
        <Command.Empty className="p-6 text-center text-sm text-system-warning">
          [ERR] No active vectors or modules found matching your query.
        </Command.Empty>

        <Command.Group heading="System Operations" className="text-xs text-gray-500 px-2 pt-3 pb-1 uppercase tracking-widest">
          <Command.Item
            onSelect={forceSync}
            className="flex items-center gap-3 px-3 py-2.5 text-sm text-gray-300 hover:bg-brand/10 hover:text-brand cursor-pointer rounded-lg aria-selected:bg-brand/10 aria-selected:text-brand aria-selected:border-l-2 aria-selected:border-brand border-l-2 border-transparent transition-all mt-1"
          >
            <RefreshCw size={16} /> Force Uplink Sync
          </Command.Item>
        </Command.Group>

        <Command.Group heading="Navigation Modules" className="text-xs text-gray-500 px-2 pt-4 pb-1 uppercase tracking-widest border-t border-surface-border/50 mt-2">
          <Command.Item onSelect={() => navigateTo('/dashboard', 'Command Center')} className="cmd-item">
            <LayoutDashboard size={16} /> Command Center
          </Command.Item>
          <Command.Item onSelect={() => navigateTo('/watchlist', 'Radar Array')} className="cmd-item">
            <ListChecks size={16} /> Radar Array (Watchlist)
          </Command.Item>
          <Command.Item onSelect={() => navigateTo('/monitoring', 'Live Telemetry')} className="cmd-item">
            <Activity size={16} /> Live Telemetry
          </Command.Item>
          <Command.Item onSelect={() => navigateTo('/positions', 'Active Vectors')} className="cmd-item">
            <TrendingUp size={16} /> Active Vectors (Positions)
          </Command.Item>
          <Command.Item onSelect={() => navigateTo('/ledger', 'Paper Ledger')} className="cmd-item">
            <BookOpen size={16} /> Paper Ledger
          </Command.Item>
          <Command.Item onSelect={() => navigateTo('/trades', 'Execution Log')} className="cmd-item">
            <Clock size={16} /> Execution Log (Trades)
          </Command.Item>
          <Command.Item onSelect={() => navigateTo('/audit', 'System Audit')} className="cmd-item">
            <FileText size={16} /> System Audit Trail
          </Command.Item>
          <Command.Item onSelect={() => navigateTo('/runtime', 'Engine Config')} className="cmd-item">
            <Settings size={16} /> Engine Config (Runtime)
          </Command.Item>
        </Command.Group>
      </Command.List>
      
      <div className="px-4 py-3 border-t border-surface-border bg-surface-card/30 flex justify-between items-center text-[10px] text-gray-600">
        <span>Forge_OS Terminal Node</span>
        <span className="flex items-center gap-2">
          Use <span className="bg-surface-border px-1.5 py-0.5 rounded text-gray-400">↑</span> <span className="bg-surface-border px-1.5 py-0.5 rounded text-gray-400">↓</span> to navigate, <span className="bg-surface-border px-1.5 py-0.5 rounded text-gray-400">↵</span> to execute
        </span>
      </div>
    </Command.Dialog>
  )
}