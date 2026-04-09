import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchTradeHistory, fetchTradeSummary } from '@/api/endpoints'
import MetricCard from '@/components/MetricCard'
import { RefreshCw, Download } from 'lucide-react'
import { formatET, relativeTime } from '@/utils/time'

interface Trade {
  id: string
  symbol: string
  asset_class: string
  entry_price: number | null
  exit_price: number | null
  quantity: number | null
  entry_time: string | null
  exit_time: string | null
  exit_reason: string | null
  entry_strategy: string | null
  exit_strategy: string | null
  pnl_realized: number | null
  fees_paid: number | null
  regime_at_entry: string | null
}

interface Summary {
  total_trades: number
  winners: number
  losers: number
  win_rate: number
  total_pnl: number
  avg_pnl: number
}

function pnlColor(v: number | null) {
  if (v == null) return 'text-gray-400'
  return v > 0 ? 'text-emerald-400' : v < 0 ? 'text-red-400' : 'text-gray-400'
}

export default function TradeHistory() {
  const [filterClass, setFilterClass] = useState<string>('')

  const params: Record<string, string> = {}
  if (filterClass) params.asset_class = filterClass

  const { data: trades = [], isLoading, refetch } = useQuery<Trade[]>({
    queryKey: ['trades', filterClass],
    queryFn: () => fetchTradeHistory(params),
    refetchInterval: 30000,
  })

  const { data: summary } = useQuery<Summary>({
    queryKey: ['trade-summary', filterClass],
    queryFn: () => fetchTradeSummary(filterClass ? { asset_class: filterClass } : {}),
    refetchInterval: 30000,
  })

  const exportCSV = () => {
    const rows = [
      ['Symbol', 'Class', 'Entry', 'Exit', 'Qty', 'Entry Time', 'Exit Time', 'PnL', 'Exit Reason', 'Strategy'],
      ...trades.map(t => [
        t.symbol,
        t.asset_class,
        t.entry_price ?? '',
        t.exit_price ?? '',
        t.quantity ?? '',
        t.entry_time ?? '',
        t.exit_time ?? '',
        t.pnl_realized ?? '',
        t.exit_reason ?? '',
        t.entry_strategy ?? '',
      ]),
    ]
    const csv = rows.map(r => r.join(',')).join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'signal_forge_trades.csv'
    a.click()
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Trade History</h1>
          <p className="text-sm text-gray-500 mt-1">{trades.length} closed trades</p>
        </div>
        <div className="flex gap-3">
          <button onClick={exportCSV} className="btn-ghost flex items-center gap-1.5">
            <Download size={14} />
            Export CSV
          </button>
          <button onClick={() => refetch()} className="btn-ghost flex items-center gap-1.5">
            <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </div>

      {/* Summary metrics */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
          <MetricCard label="Total Trades" value={summary.total_trades} />
          <MetricCard label="Winners" value={summary.winners} positive={summary.winners > 0} />
          <MetricCard label="Losers" value={summary.losers} negative={summary.losers > 0} />
          <MetricCard label="Win Rate" value={`${summary.win_rate}%`} positive={summary.win_rate >= 50} />
          <MetricCard
            label="Total PnL"
            value={(summary.total_pnl >= 0 ? '+' : '') + summary.total_pnl.toFixed(2)}
            positive={summary.total_pnl > 0}
            negative={summary.total_pnl < 0}
            mono
          />
          <MetricCard
            label="Avg PnL"
            value={(summary.avg_pnl >= 0 ? '+' : '') + summary.avg_pnl.toFixed(2)}
            positive={summary.avg_pnl > 0}
            negative={summary.avg_pnl < 0}
            mono
          />
        </div>
      )}

      {/* Filters */}
      <div className="flex gap-3">
        {['', 'crypto', 'stock'].map(c => (
          <button
            key={c}
            onClick={() => setFilterClass(c)}
            className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
              filterClass === c ? 'bg-brand text-white' : 'bg-surface-card text-gray-400 hover:text-white'
            }`}
          >
            {c || 'All'}
          </button>
        ))}
      </div>

      {/* Trades table */}
      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-surface-border text-xs text-gray-500 uppercase tracking-wider">
              <th className="text-left px-5 py-3">Symbol</th>
              <th className="text-left px-5 py-3">Class</th>
              <th className="text-right px-5 py-3">Entry</th>
              <th className="text-right px-5 py-3">Exit</th>
              <th className="text-right px-5 py-3">PnL</th>
              <th className="text-left px-5 py-3">Exit Reason</th>
              <th className="text-left px-5 py-3">Strategy</th>
              <th className="text-left px-5 py-3">Closed</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr><td colSpan={8} className="px-5 py-8 text-center text-gray-500">Loading…</td></tr>
            )}
            {!isLoading && trades.length === 0 && (
              <tr><td colSpan={8} className="px-5 py-8 text-center text-gray-500">No closed trades yet</td></tr>
            )}
            {trades.map(t => (
              <tr key={t.id} className="border-b border-surface-border/50 table-row-hover">
                <td className="px-5 py-3 mono font-medium text-white">{t.symbol}</td>
                <td className="px-5 py-3">
                  <span className={`badge ${t.asset_class === 'crypto' ? 'bg-violet-500/20 text-violet-400 border border-violet-500/30' : 'bg-sky-500/20 text-sky-400 border border-sky-500/30'}`}>
                    {t.asset_class}
                  </span>
                </td>
                <td className="px-5 py-3 text-right mono text-gray-300">{t.entry_price?.toFixed(4) ?? '—'}</td>
                <td className="px-5 py-3 text-right mono text-gray-300">{t.exit_price?.toFixed(4) ?? '—'}</td>
                <td className={`px-5 py-3 text-right mono font-medium ${pnlColor(t.pnl_realized)}`}>
                  {t.pnl_realized != null ? (t.pnl_realized >= 0 ? '+' : '') + t.pnl_realized.toFixed(4) : '—'}
                </td>
                <td className="px-5 py-3 text-gray-400 text-xs max-w-[160px] truncate">{t.exit_reason || '—'}</td>
                <td className="px-5 py-3 text-gray-500 text-xs max-w-[140px] truncate">{t.entry_strategy || '—'}</td>
                <td className="px-5 py-3 text-gray-400 text-xs whitespace-nowrap">
                  {t.exit_time
                    ? <span title={relativeTime(t.exit_time)}>{formatET(t.exit_time)}</span>
                    : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
