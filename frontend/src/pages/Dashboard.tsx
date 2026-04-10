import { useQuery } from '@tanstack/react-query'
import { fetchDashboard, fetchMarketStatus } from '@/api/endpoints'
import type { MarketStatusResponse } from '@/api/types'
import MetricCard from '@/components/MetricCard'
import StatusBadge from '@/components/StatusBadge'
import { useWebSocket } from '@/providers/WebSocketProvider'
import {
  Activity,
  TrendingUp,
  ListChecks,
  Wifi,
  WifiOff,
  RefreshCw,
  Cpu,
  Server
} from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import clsx from 'clsx'

interface PnlSummary {
  asset_class: string
  realized_pnl: number
  unrealized_pnl: number
  cash_balance: number
  fees_total: number
  open_positions: number
}

interface DashboardData {
  system_status: string
  trading_enabled: boolean
  crypto_trading_enabled: boolean
  stock_trading_enabled: boolean
  crypto_monitor: string
  stock_monitor: string
  crypto_exit_worker: string
  stock_exit_worker: string
  discord_listener: string
  last_heartbeat: string | null
  pnl: PnlSummary[]
  total_open_positions: number
  active_watchlist_count: number
  managed_watchlist_count: number
}

function stockStatus(raw: string, ms: MarketStatusResponse['status']): string {
  if (ms === 'closed') return 'paused'
  if (ms === 'pre_market') return 'pre-market'
  if (ms === 'eod') return 'eod'
  return raw
}

const workerNodes: Array<{ key: keyof DashboardData; label: string; isStock: boolean }> = [
  { key: 'crypto_monitor', label: 'CRYPTO_MON', isStock: false },
  { key: 'stock_monitor', label: 'STOCK_MON', isStock: true },
  { key: 'crypto_exit_worker', label: 'CRYPTO_EXT', isStock: false },
  { key: 'stock_exit_worker', label: 'STOCK_EXT', isStock: true },
  { key: 'discord_listener', label: 'DISCORD_IO', isStock: false },
]

function fmt(n: number) {
  return (n >= 0 ? '+' : '') + n.toFixed(2)
}

export default function Dashboard() {
  const { status: wsStatus } = useWebSocket()
  
  // Notice: refetchInterval has been REMOVED. WSS now drives data invalidation.
  const qDash = useQuery({ queryKey: ['dashboard'], queryFn: fetchDashboard, staleTime: Infinity }) as { data?: DashboardData; isLoading?: boolean; isError?: boolean; dataUpdatedAt?: number; refetch?: () => Promise<any> }
  const data = qDash.data
  const isLoading = qDash.isLoading
  const isError = qDash.isError
  const dataUpdatedAt = qDash.dataUpdatedAt
  const refetch = qDash.refetch

  const qMarket = useQuery({ queryKey: ['market-status'], queryFn: fetchMarketStatus, staleTime: Infinity }) as { data?: MarketStatusResponse }
  const marketData = qMarket.data
  const ms = marketData?.status ?? 'open'

  const cryptoPnl = data?.pnl.find(p => p.asset_class === 'crypto')
  const stockPnl = data?.pnl.find(p => p.asset_class === 'stock')
  const totalRealized = (cryptoPnl?.realized_pnl ?? 0) + (stockPnl?.realized_pnl ?? 0)
  const totalUnrealized = (cryptoPnl?.unrealized_pnl ?? 0) + (stockPnl?.unrealized_pnl ?? 0)

  const sparkData = [
    { name: 'Crypto', value: cryptoPnl?.realized_pnl ?? 0 },
    { name: 'Stock', value: stockPnl?.realized_pnl ?? 0 },
    { name: 'Aggregate', value: totalRealized },
  ]

  return (
    <div className="space-y-6 max-w-[1600px] mx-auto pb-10">
      {/* Header & Main Connection Status */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 border-b border-surface-border pb-4">
        <div>
          <h1 className="text-3xl font-bold text-white tracking-tight">Main Telemetry</h1>
          <div className="flex items-center gap-3 mt-2 mono text-xs">
            <span className="text-gray-500">SYNC:</span>
            <span className={clsx("font-medium", wsStatus === 'connected' ? "text-brand" : "text-system-warning")}>
              {wsStatus === 'connected' ? 'REAL-TIME STREAM' : dataUpdatedAt ? new Date(dataUpdatedAt).toISOString() : 'AWAITING_DATA'}
            </span>
            <span className="text-gray-600">|</span>
            <span className="text-gray-500">LAST_PACKET:</span>
            <span className="text-white">{dataUpdatedAt ? formatDistanceToNow(new Date(dataUpdatedAt)) : '---'}</span>
          </div>
        </div>
        <div className="flex items-center gap-4 bg-surface-card border border-surface-border p-2 rounded-lg relative overflow-hidden group">
          {wsStatus === 'connected' && (
            <div className="absolute inset-0 bg-brand/5 pointer-events-none group-hover:bg-brand/10 transition-colors"></div>
          )}
          {data && (
            <div className="flex items-center gap-3 px-3 relative z-10">
              <div className="flex items-center gap-2">
                {data.system_status === 'online' ? (
                  <Wifi size={18} className="text-system-online animate-pulse-slow" />
                ) : (
                  <WifiOff size={18} className="text-system-offline" />
                )}
                <span className="text-xs font-mono uppercase text-gray-400">Core Engine</span>
              </div>
              <StatusBadge status={data.system_status} showRaw />
            </div>
          )}
          <div className="w-[1px] h-6 bg-surface-border relative z-10"></div>
          <button
            onClick={() => refetch()}
            className="btn-ghost flex items-center gap-2 px-4 py-1.5 relative z-10"
            disabled={isLoading || wsStatus === 'connecting'}
          >
            <RefreshCw size={14} className={isLoading ? 'animate-spin text-brand' : ''} />
            <span className="mono uppercase text-xs">Force Sync</span>
          </button>
        </div>
      </div>

      {isError && (
        <div className="card border-system-offline/50 bg-system-offline/10 text-system-offline mono text-sm flex items-center gap-3 shadow-[inset_0_0_20px_rgba(239,68,68,0.1)]">
          <Activity size={18} className="animate-pulse" />
          [ERR_CONN_REFUSED] UNABLE TO ESTABLISH UPLINK TO PORT 8100.
        </div>
      )}

      {/* Worker Rack (Server Layout) */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {workerNodes.map(({ key, label, isStock }) => {
          const rawStatus = data ? String(data[key]) : 'offline'
          const nodeStatus = isStock ? stockStatus(rawStatus, ms) : rawStatus
          const isOnline = nodeStatus === 'online' || nodeStatus === 'running'
          
          return (
            <div key={key} className={clsx(
              "card py-3 px-4 flex flex-col gap-2 border-l-2 transition-colors duration-500",
              isOnline ? "border-l-system-online bg-system-online/5" : "border-l-surface-border"
            )}>
              <div className="flex justify-between items-center">
                <span className="text-xs text-gray-400 mono font-medium">{label}</span>
                <Server size={12} className={isOnline ? 'text-system-online drop-shadow-[0_0_5px_rgba(16,185,129,0.5)]' : 'text-gray-600'} />
              </div>
              <div>
                <StatusBadge status={data ? nodeStatus : 'unknown'} showRaw={true} />
              </div>
            </div>
          )
        })}
      </div>

      {/* Top Metrics Array */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricCard
          label="Active Vectors (Pos)"
          value={data?.total_open_positions ?? '—'}
          icon={<TrendingUp size={16} className="text-brand" />}
        />
        <MetricCard
          label="Radar Signatures (WL)"
          value={data?.active_watchlist_count ?? '—'}
          sub={`[ ${data?.managed_watchlist_count ?? 0} MNGD ]`}
          icon={<ListChecks size={16} className="text-brand" />}
        />
        <MetricCard
          label="Realized Delta"
          value={isLoading ? '—' : fmt(totalRealized)}
          icon={<Cpu size={16} className="text-brand" />}
          positive={totalRealized > 0}
          negative={totalRealized < 0}
          mono
        />
        <MetricCard
          label="Unrealized Delta"
          value={isLoading ? '—' : fmt(totalUnrealized)}
          positive={totalUnrealized > 0}
          negative={totalUnrealized < 0}
          mono
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* PnL Subsystems */}
        <div className="lg:col-span-1 space-y-6">
          {/* Crypto Panel */}
          <div className="card space-y-4">
            <div className="flex items-center justify-between border-b border-surface-border pb-3">
              <div className="text-xs text-gray-400 mono font-bold uppercase tracking-widest flex items-center gap-2">
                <div className="w-1.5 h-1.5 rounded-full bg-[#5865F2] shadow-[0_0_8px_rgba(88,101,242,0.8)]"></div>
                Node_A: Crypto
              </div>
              <StatusBadge status={data?.crypto_trading_enabled ? 'ACTIVE' : 'INACTIVE'} />
            </div>
            <div className="space-y-3 text-sm">
              <Row label="Realized_PnL" value={fmt(cryptoPnl?.realized_pnl ?? 0)} colored />
              <Row label="Unrealized_PnL" value={fmt(cryptoPnl?.unrealized_pnl ?? 0)} colored />
              <Row label="Liquidity" value={(cryptoPnl?.cash_balance ?? 0).toFixed(2)} />
              <Row label="Network_Fees" value={(cryptoPnl?.fees_total ?? 0).toFixed(4)} />
              <Row label="Open_Ops" value={String(cryptoPnl?.open_positions ?? 0)} />
            </div>
          </div>

          {/* Stocks Panel */}
          <div className="card space-y-4">
            <div className="flex items-center justify-between border-b border-surface-border pb-3">
              <div className="text-xs text-gray-400 mono font-bold uppercase tracking-widest flex items-center gap-2">
                <div className="w-1.5 h-1.5 rounded-full bg-[#10b981] shadow-[0_0_8px_rgba(16,185,129,0.8)]"></div>
                Node_B: Stocks
              </div>
              <StatusBadge status={data?.stock_trading_enabled ? 'ACTIVE' : 'INACTIVE'} />
            </div>
            <div className="space-y-3 text-sm">
              <Row label="Realized_PnL" value={fmt(stockPnl?.realized_pnl ?? 0)} colored />
              <Row label="Unrealized_PnL" value={fmt(stockPnl?.unrealized_pnl ?? 0)} colored />
              <Row label="Liquidity" value={(stockPnl?.cash_balance ?? 0).toFixed(2)} />
              <Row label="Broker_Fees" value={(stockPnl?.fees_total ?? 0).toFixed(4)} />
              <Row label="Open_Ops" value={String(stockPnl?.open_positions ?? 0)} />
            </div>
          </div>
        </div>

        {/* Global PnL Chart Terminal */}
        <div className="lg:col-span-2 card flex flex-col relative z-10">
          <div className="flex items-center justify-between mb-6">
            <div className="text-xs text-brand mono font-bold uppercase tracking-widest drop-shadow-[0_0_5px_rgba(99,102,241,0.5)]">Global PnL Trajectory</div>
            <div className="text-[10px] text-system-online mono border border-system-online/30 px-2 py-1 rounded bg-system-online/10 animate-pulse">STREAM_ACTIVE</div>
          </div>
          <div className="flex-1 min-h-[300px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={sparkData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="pnlGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#6366f1" stopOpacity={0.5} />
                    <stop offset="100%" stopColor="#6366f1" stopOpacity={0.0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2335" vertical={false} />
                <XAxis 
                  dataKey="name" 
                  tick={{ fill: '#6b7280', fontSize: 12, fontFamily: 'JetBrains Mono' }} 
                  axisLine={false} 
                  tickLine={false} 
                  dy={10}
                />
                <YAxis 
                  tick={{ fill: '#6b7280', fontSize: 12, fontFamily: 'JetBrains Mono' }} 
                  axisLine={false} 
                  tickLine={false} 
                  width={60} 
                  tickFormatter={(val) => `$${val}`}
                />
                <Tooltip
                  contentStyle={{ 
                    background: 'rgba(18, 20, 31, 0.95)', 
                    border: '1px solid #2a2d3e', 
                    borderRadius: 8, 
                    fontFamily: 'JetBrains Mono',
                    boxShadow: '0 0 15px rgba(99, 102, 241, 0.3)',
                    backdropFilter: 'blur(4px)'
                  }}
                  labelStyle={{ color: '#9ca3af', marginBottom: '4px' }}
                  itemStyle={{ color: '#fff', fontWeight: 'bold' }}
                  cursor={{ stroke: '#6366f1', strokeWidth: 1, strokeDasharray: '4 4' }}
                  animationDuration={300}
                />
                <Area 
                  type="monotone" 
                  dataKey="value" 
                  stroke="#6366f1" 
                  strokeWidth={3} 
                  fill="url(#pnlGrad)"
                  activeDot={{ r: 6, fill: '#6366f1', stroke: '#fff', strokeWidth: 2, className: 'drop-shadow-[0_0_8px_rgba(99,102,241,0.8)]' }}
                  animationDuration={1000}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  )
}

function Row({ label, value, colored }: { label: string; value: string; colored?: boolean }) {
  const n = parseFloat(value)
  return (
    <div className="flex justify-between items-center group">
      <span className="text-gray-500 mono text-xs group-hover:text-gray-400 transition-colors">{label}</span>
      <span className={clsx(
        "font-mono text-sm tracking-tight transition-colors duration-300",
        colored
          ? n > 0 ? 'text-system-online drop-shadow-[0_0_8px_rgba(16,185,129,0.3)]' 
            : n < 0 ? 'text-system-offline drop-shadow-[0_0_8px_rgba(239,68,68,0.3)]' 
            : 'text-gray-300'
          : 'text-gray-200'
      )}>
        {value}
      </span>
    </div>
  )
}