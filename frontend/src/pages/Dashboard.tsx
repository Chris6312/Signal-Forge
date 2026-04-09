import { useQuery } from '@tanstack/react-query'
import { fetchDashboard, fetchMarketStatus } from '@/api/endpoints'
import type { MarketStatusResponse } from '@/api/types'
import MetricCard from '@/components/MetricCard'
import StatusBadge from '@/components/StatusBadge'
import {
  Activity,
  TrendingUp,
  ListChecks,
  Wifi,
  WifiOff,
  RefreshCw,
} from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'

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
  if (ms === 'closed')     return 'paused'
  if (ms === 'pre_market') return 'pre-market'
  if (ms === 'eod')        return 'eod'
  return raw
}

const workerKeys: Array<{ key: keyof DashboardData; label: string; isStock: boolean }> = [
  { key: 'crypto_monitor',    label: 'Crypto Monitor', isStock: false },
  { key: 'stock_monitor',     label: 'Stock Monitor',  isStock: true  },
  { key: 'crypto_exit_worker',label: 'Crypto Exit',    isStock: false },
  { key: 'stock_exit_worker', label: 'Stock Exit',     isStock: true  },
  { key: 'discord_listener',  label: 'Discord',        isStock: false },
]

function fmt(n: number) {
  return (n >= 0 ? '+' : '') + n.toFixed(2)
}

export default function Dashboard() {
  const { data, isLoading, isError, dataUpdatedAt, refetch } = useQuery<DashboardData>({
    queryKey: ['dashboard'],
    queryFn: fetchDashboard,
    refetchInterval: 15000,
  })

  const { data: marketData } = useQuery<MarketStatusResponse>({
    queryKey: ['market-status'],
    queryFn: fetchMarketStatus,
    refetchInterval: 60_000,
    staleTime: 30_000,
  })
  const ms = marketData?.status ?? 'open'

  const cryptoPnl = data?.pnl.find(p => p.asset_class === 'crypto')
  const stockPnl = data?.pnl.find(p => p.asset_class === 'stock')
  const totalRealized = (cryptoPnl?.realized_pnl ?? 0) + (stockPnl?.realized_pnl ?? 0)
  const totalUnrealized = (cryptoPnl?.unrealized_pnl ?? 0) + (stockPnl?.unrealized_pnl ?? 0)

  const sparkData = [
    { name: 'Crypto', value: cryptoPnl?.realized_pnl ?? 0 },
    { name: 'Stock', value: stockPnl?.realized_pnl ?? 0 },
    { name: 'Total', value: totalRealized },
  ]

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Dashboard</h1>
          <p className="text-sm text-gray-500 mt-1">
            {dataUpdatedAt
              ? `Updated ${formatDistanceToNow(new Date(dataUpdatedAt))} ago`
              : 'Loading…'}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {data && (
            <div className="flex items-center gap-2">
              {data.system_status === 'online' ? (
                <Wifi size={16} className="text-emerald-400" />
              ) : (
                <WifiOff size={16} className="text-red-400" />
              )}
              <StatusBadge status={data.system_status} />
            </div>
          )}
          <button
            onClick={() => refetch()}
            className="btn-ghost flex items-center gap-1.5"
            disabled={isLoading}
          >
            <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </div>

      {isError && (
        <div className="card border-red-500/30 bg-red-500/10 text-red-400 text-sm">
          ⚠ Unable to connect to Signal Forge backend. Make sure the backend is running on port 8100.
        </div>
      )}

      {/* Top metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricCard
          label="Total Open Positions"
          value={data?.total_open_positions ?? '—'}
          icon={<TrendingUp size={14} />}
        />
        <MetricCard
          label="Active Watchlist"
          value={data?.active_watchlist_count ?? '—'}
          sub={`${data?.managed_watchlist_count ?? 0} managed`}
          icon={<ListChecks size={14} />}
        />
        <MetricCard
          label="Realized PnL"
          value={isLoading ? '—' : fmt(totalRealized)}
          icon={<Activity size={14} />}
          positive={totalRealized > 0}
          negative={totalRealized < 0}
          mono
        />
        <MetricCard
          label="Unrealized PnL"
          value={isLoading ? '—' : fmt(totalUnrealized)}
          positive={totalUnrealized > 0}
          negative={totalUnrealized < 0}
          mono
        />
      </div>

      {/* PnL by asset class + chart */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Crypto */}
        <div className="card space-y-3">
          <div className="text-xs text-gray-400 uppercase tracking-wider font-medium">Crypto (Kraken)</div>
          <div className="space-y-2 text-sm">
            <Row label="Realized PnL" value={fmt(cryptoPnl?.realized_pnl ?? 0)} colored />
            <Row label="Unrealized PnL" value={fmt(cryptoPnl?.unrealized_pnl ?? 0)} colored />
            <Row label="Cash Balance" value={(cryptoPnl?.cash_balance ?? 0).toFixed(2)} />
            <Row label="Fees Paid" value={(cryptoPnl?.fees_total ?? 0).toFixed(4)} />
            <Row label="Open Positions" value={String(cryptoPnl?.open_positions ?? 0)} />
          </div>
          <div className="flex items-center gap-2 pt-1">
            <StatusBadge status={data?.crypto_trading_enabled ? 'ACTIVE' : 'INACTIVE'} />
            <span className="text-xs text-gray-500">trading</span>
          </div>
        </div>

        {/* Stocks */}
        <div className="card space-y-3">
          <div className="text-xs text-gray-400 uppercase tracking-wider font-medium">Stocks (Tradier)</div>
          <div className="space-y-2 text-sm">
            <Row label="Realized PnL" value={fmt(stockPnl?.realized_pnl ?? 0)} colored />
            <Row label="Unrealized PnL" value={fmt(stockPnl?.unrealized_pnl ?? 0)} colored />
            <Row label="Cash Balance" value={(stockPnl?.cash_balance ?? 0).toFixed(2)} />
            <Row label="Fees Paid" value={(stockPnl?.fees_total ?? 0).toFixed(4)} />
            <Row label="Open Positions" value={String(stockPnl?.open_positions ?? 0)} />
          </div>
          <div className="flex items-center gap-2 pt-1">
            <StatusBadge status={data?.stock_trading_enabled ? 'ACTIVE' : 'INACTIVE'} />
            <span className="text-xs text-gray-500">trading</span>
          </div>
        </div>

        {/* PnL Chart */}
        <div className="card flex flex-col gap-3">
          <div className="text-xs text-gray-400 uppercase tracking-wider font-medium">PnL Overview</div>
          <div className="flex-1 h-40">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={sparkData}>
                <defs>
                  <linearGradient id="pnlGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="name" tick={{ fill: '#6b7280', fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#6b7280', fontSize: 11 }} axisLine={false} tickLine={false} width={50} />
                <Tooltip
                  contentStyle={{ background: '#1a1d2e', border: '1px solid #2a2d3e', borderRadius: 8, fontSize: 12 }}
                  labelStyle={{ color: '#d1d5db' }}
                  itemStyle={{ color: '#a5b4fc' }}
                />
                <Area type="monotone" dataKey="value" stroke="#6366f1" strokeWidth={2} fill="url(#pnlGrad)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Workers */}
      <div className="card">
        <div className="text-xs text-gray-400 uppercase tracking-wider font-medium mb-4">Worker Status</div>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          {workerKeys.map(({ key, label, isStock }) => (
            <div key={key} className="flex flex-col gap-1.5">
              <span className="text-xs text-gray-500">{label}</span>
              <StatusBadge status={data
                ? (isStock ? stockStatus(String(data[key]), ms) : String(data[key]))
                : 'unknown'
              } />
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function Row({ label, value, colored }: { label: string; value: string; colored?: boolean }) {
  const n = parseFloat(value)
  return (
    <div className="flex justify-between items-center">
      <span className="text-gray-500">{label}</span>
      <span className={colored
        ? n > 0 ? 'text-emerald-400 mono' : n < 0 ? 'text-red-400 mono' : 'text-gray-300 mono'
        : 'text-gray-300 mono'
      }>
        {value}
      </span>
    </div>
  )
}
