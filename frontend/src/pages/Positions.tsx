import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchPositions } from '@/api/endpoints'
import StatusBadge from '@/components/StatusBadge'
import { RefreshCw, ChevronDown, ChevronUp } from 'lucide-react'
import { formatET, relativeTime } from '@/utils/time'

interface Position {
  id: string
  symbol: string
  asset_class: string
  state: string
  entry_price: number | null
  current_price: number | null
  quantity: number | null
  entry_time: string | null
  entry_strategy: string | null
  exit_strategy: string | null
  initial_stop: number | null
  current_stop: number | null
  profit_target_1: number | null
  profit_target_2: number | null
  max_hold_hours: number | null
  regime_at_entry: string | null
  milestone_state: Record<string, unknown> | null
  frozen_policy: Record<string, unknown> | null
  pnl_unrealized: number | null
  pnl_realized: number | null
  management_policy_version: string | null
}

function pnlColor(v: number | null) {
  if (v == null) return 'text-gray-400'
  return v > 0 ? 'text-emerald-400' : v < 0 ? 'text-red-400' : 'text-gray-400'
}

function fmt4(v: number | null) {
  return v == null ? '—' : v.toFixed(4)
}

function fmtQty(v: number | null) {
  if (v == null) return '—'
  if (v === 0) return '0'
  return v % 1 === 0 ? v.toString() : parseFloat(v.toFixed(8)).toString()
}

function pct(entry: number | null, current: number | null) {
  if (!entry || !current) return null
  return ((current - entry) / entry * 100)
}

export default function Positions() {
  const [filterState, setFilterState] = useState<string>('OPEN')
  const [filterClass, setFilterClass] = useState<string>('')
  const [expanded, setExpanded] = useState<string | null>(null)

  const params: Record<string, string> = {}
  if (filterState) params.state = filterState
  if (filterClass) params.asset_class = filterClass

  const { data = [], isLoading, refetch } = useQuery<Position[]>({
    queryKey: ['positions', filterState, filterClass],
    queryFn: () => fetchPositions(params),
    refetchInterval: 15000,
  })

  const open = data.filter(p => p.state === 'OPEN')
  const closed = data.filter(p => p.state === 'CLOSED')

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Positions</h1>
          <p className="text-sm text-gray-500 mt-1">
            {open.length} open · {closed.length} closed
          </p>
        </div>
        <button onClick={() => refetch()} className="btn-ghost flex items-center gap-1.5">
          <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {/* Filters */}
      <div className="flex gap-3 flex-wrap">
        {['OPEN', '', 'CLOSED'].map(s => (
          <button
            key={s}
            onClick={() => setFilterState(s)}
            className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
              filterState === s ? 'bg-brand text-white' : 'bg-surface-card text-gray-400 hover:text-white'
            }`}
          >
            {s || 'All'}
          </button>
        ))}
        <div className="w-px bg-surface-border mx-1" />
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

      {/* Positions table */}
      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-surface-border text-xs text-gray-500 uppercase tracking-wider">
              <th className="text-left px-5 py-3">Symbol</th>
              <th className="text-left px-5 py-3">Class</th>
              <th className="text-left px-5 py-3">State</th>
              <th className="text-right px-5 py-3">Entry</th>
              <th className="text-right px-5 py-3">Qty</th>
              <th className="text-right px-5 py-3">Current</th>
              <th className="text-right px-5 py-3">Stop</th>
              <th className="text-right px-5 py-3">TP1</th>
              <th className="text-right px-5 py-3">Unreal. PnL</th>
              <th className="text-left px-5 py-3">Strategy</th>
              <th className="px-5 py-3" />
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr><td colSpan={11} className="px-5 py-8 text-center text-gray-500">Loading…</td></tr>
            )}
            {!isLoading && data.length === 0 && (
              <tr><td colSpan={11} className="px-5 py-8 text-center text-gray-500">No positions</td></tr>
            )}
            {data.map(pos => {
              const change = pct(pos.entry_price, pos.current_price)
              const isExpanded = expanded === pos.id
              return (
                <>
                  <tr key={pos.id} className="border-b border-surface-border/50 table-row-hover">
                    <td className="px-5 py-3 mono font-medium text-white">{pos.symbol}</td>
                    <td className="px-5 py-3">
                      <span className={`badge ${pos.asset_class === 'crypto' ? 'bg-violet-500/20 text-violet-400 border border-violet-500/30' : 'bg-sky-500/20 text-sky-400 border border-sky-500/30'}`}>
                        {pos.asset_class}
                      </span>
                    </td>
                    <td className="px-5 py-3"><StatusBadge status={pos.state} /></td>
                    <td className="px-5 py-3 text-right mono text-gray-300">{fmt4(pos.entry_price)}</td>
                    <td className="px-5 py-3 text-right mono text-gray-300">{fmtQty(pos.quantity)}</td>
                    <td className="px-5 py-3 text-right mono">
                      <span className={change != null ? (change > 0 ? 'text-emerald-400' : 'text-red-400') : 'text-gray-300'}>
                        {fmt4(pos.current_price)}
                        {change != null && <span className="text-xs ml-1">({change > 0 ? '+' : ''}{change.toFixed(2)}%)</span>}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-right mono text-red-400">{fmt4(pos.current_stop)}</td>
                    <td className="px-5 py-3 text-right mono text-emerald-400">{fmt4(pos.profit_target_1)}</td>
                    <td className={`px-5 py-3 text-right mono ${pnlColor(pos.pnl_unrealized)}`}>
                      {pos.pnl_unrealized != null ? (pos.pnl_unrealized >= 0 ? '+' : '') + pos.pnl_unrealized.toFixed(2) : '—'}
                    </td>
                    <td className="px-5 py-3 text-gray-400 text-xs max-w-[160px] truncate">{pos.entry_strategy || '—'}</td>
                    <td className="px-5 py-3">
                      <button onClick={() => setExpanded(isExpanded ? null : pos.id)} className="text-gray-500 hover:text-white">
                        {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                      </button>
                    </td>
                  </tr>

                  {isExpanded && (
                    <tr key={pos.id + '-detail'} className="border-b border-surface-border bg-surface/50">
                      <td colSpan={11} className="px-5 py-4">
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
                          <div className="space-y-1">
                            <div className="text-gray-500 uppercase tracking-wider">Entry Details</div>
                            <div className="text-gray-400">Entry: <span className="mono text-white">{fmt4(pos.entry_price)}</span></div>
                            <div className="text-gray-400">Qty: <span className="mono text-white">{pos.quantity ?? '—'}</span></div>
                            <div className="text-gray-400">Time: <span className="text-white" title={relativeTime(pos.entry_time)}>{formatET(pos.entry_time)}</span></div>
                            <div className="text-gray-400">Regime: <span className="text-white">{pos.regime_at_entry || '—'}</span></div>
                          </div>
                          <div className="space-y-1">
                            <div className="text-gray-500 uppercase tracking-wider">Frozen Policy</div>
                            <div className="text-gray-400">Entry Strategy: <span className="text-white">{pos.entry_strategy || '—'}</span></div>
                            <div className="text-gray-400">Exit Strategy: <span className="text-white">{pos.exit_strategy || '—'}</span></div>
                            <div className="text-gray-400">Initial Stop: <span className="mono text-red-400">{fmt4(pos.initial_stop)}</span></div>
                            <div className="text-gray-400">Max Hold: <span className="text-white">{pos.max_hold_hours ? pos.max_hold_hours + 'h' : '—'}</span></div>
                          </div>
                          <div className="space-y-1">
                            <div className="text-gray-500 uppercase tracking-wider">Targets</div>
                            <div className="text-gray-400">TP1: <span className="mono text-emerald-400">{fmt4(pos.profit_target_1)}</span></div>
                            <div className="text-gray-400">TP2: <span className="mono text-emerald-400">{fmt4(pos.profit_target_2)}</span></div>
                            <div className="text-gray-400">Current Stop: <span className="mono text-red-400">{fmt4(pos.current_stop)}</span></div>
                            <div className="text-gray-400">Policy v: <span className="text-white">{pos.management_policy_version || '—'}</span></div>
                          </div>
                          <div className="space-y-1">
                            <div className="text-gray-500 uppercase tracking-wider">Milestones</div>
                            {pos.milestone_state
                              ? Object.entries(pos.milestone_state).map(([k, v]) => (
                                  <div key={k} className="text-gray-400">{k}: <span className="mono text-white">{String(v)}</span></div>
                                ))
                              : <div className="text-gray-500">None</div>
                            }
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
