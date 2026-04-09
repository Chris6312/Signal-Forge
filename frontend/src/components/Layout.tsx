import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import GlobalKillSwitch from './GlobalKillSwitch'
import WebSocketProvider, { useWebSocket } from '@/providers/WebSocketProvider'
import CommandPalette from './CommandPalette'
import { Activity, WifiOff, RefreshCcw, Command as CmdIcon } from 'lucide-react'
import { Toaster } from 'sonner'
import clsx from 'clsx'

// Separate component to consume the WSS context
function GlobalHeader() {
  const { status } = useWebSocket()

  return (
    <header className="h-14 border-b border-surface-border bg-surface-card/40 flex items-center justify-between px-6 shrink-0 z-20 backdrop-blur-md">
      {/* Live WSS Telemetry Indicator */}
      <div className="flex items-center gap-3 text-xs mono">
        {status === 'connected' ? (
          <>
            <Activity size={14} className="text-system-online animate-pulse-slow drop-shadow-[0_0_5px_rgba(16,185,129,0.5)]" />
            <span className="text-gray-400">STREAM:</span>
            <span className="text-system-online font-bold tracking-widest uppercase drop-shadow-[0_0_5px_rgba(16,185,129,0.3)]">LIVE</span>
          </>
        ) : status === 'connecting' ? (
          <>
            <RefreshCcw size={14} className="text-system-warning animate-spin" />
            <span className="text-gray-400">STREAM:</span>
            <span className="text-system-warning font-bold tracking-widest uppercase">SYNCING</span>
          </>
        ) : (
          <>
            <WifiOff size={14} className="text-system-offline" />
            <span className="text-gray-400">STREAM:</span>
            <span className="text-system-offline font-bold tracking-widest uppercase">DISCONNECTED</span>
          </>
        )}
      </div>
      
      {/* Right side of header - Global Controls */}
      <div className="flex items-center gap-4">
        {/* Omnibar Hint */}
        <div className="hidden md:flex items-center gap-1.5 text-[10px] mono text-gray-500 bg-surface border border-surface-border px-2 py-1 rounded">
          <CmdIcon size={10} />
          <span>+ K to Command</span>
        </div>
        
        <div className="h-4 w-[1px] bg-surface-border"></div>
        <GlobalKillSwitch />
      </div>
    </header>
  )
}

export default function Layout() {
  return (
    <div className="flex h-screen bg-surface overflow-hidden selection:bg-brand selection:text-white">
      <Sidebar />
      <div className="flex-1 flex flex-col h-full relative">
        <WebSocketProvider>
          <GlobalHeader />
          <main className="flex-1 overflow-auto relative">
            {/* Ambient Background Glow for depth */}
            <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[300px] bg-brand/5 blur-[120px] pointer-events-none z-0 rounded-full"></div>
            
            <div className="max-w-[1600px] mx-auto px-6 py-6 pb-20 relative z-10">
              <Outlet />
            </div>
          </main>
        </WebSocketProvider>
      </div>

      {/* Global Interfaces */}
      <CommandPalette />
      
      {/* Terminal Notification Engine */}
      <Toaster 
        position="bottom-right" 
        theme="dark"
        toastOptions={{
          classNames: {
            toast: 'bg-[#12141f] border border-surface-border font-mono text-xs shadow-card-inset',
            title: 'text-white font-bold uppercase tracking-wider',
            description: 'text-gray-400 mt-1',
            success: 'border-l-2 border-l-system-online bg-system-online/5 text-gray-200',
            error: 'border-l-2 border-l-system-offline bg-system-offline/5 text-gray-200',
            warning: 'border-l-2 border-l-system-warning bg-system-warning/5 text-gray-200',
            info: 'border-l-2 border-l-brand bg-brand/5 text-gray-200',
          }
        }} 
      />
    </div>
  )
}