import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchAuditEvents, fetchEventTypes } from '@/api/endpoints'
import { RefreshCw, Filter } from 'lucide-react'
import { formatET, relativeTime } from '@/utils/time'
import clsx from 'clsx'

interface AuditEvent {
  id: string
  event_type: string
  asset_class: string | null
  symbol: string | null
  position_id: string | null
  source: string
  event_data: Record<string, unknown> | null
  message: string | null
  created_at: string | null
}

const sourceColors: Record<string, string> = {
  SYSTEM: 'bg-gray-500/20 text-gray-400 border border-gray-500/30',
  DISCORD: 'bg-indigo-500/20 text-indigo-400 border border-indigo-500/30',
  USER: 'bg-sky-500/20 text-sky-400 border border-sky-500/30',
  BROKER: 'bg-amber-500/20 text-amber-400 border border-amber-500/30',
  WORKER: 'bg-purple-500/20 text-purple-400 border border-purple-500/30',
}

const eventTypeColors: Record<string, string> = {
  POSITION_OPENED: 'text-emerald-400',
  POSITION_CLOSED: 'text-gray-400',
  STOP_UPDATED: 'text-amber-400',
  PARTIAL_EXIT: 'text-sky-400',
  WATCHLIST_UPDATED: 'text-brand',
  WATCHLIST_SYMBOL_MANAGED: 'text-amber-400',
  WATCHLIST_SYMBOL_REMOVED: 'text-red-400',
}

export default function AuditTrail() {
  const [filterType, setFilterType] = useState('')
  const [filterSymbol, setFilterSymbol] = useState('')
  const [filterSource, setFilterSource] = useState('')
  const [filterClass, setFilterClass] = useState('')
  const [expanded, setExpanded] = useState<string | null>(null)
  const [filtersOpen, setFiltersOpen] = useState(false)

  const params: Record<string, string> = { limit: '200' }
  if (filterType) params.event_type = filterType
  if (filterSymbol) params.symbol = filterSymbol.toUpperCase()
  if (filterSource) params.source = filterSource
  if (filterClass) params.asset_class = filterClass

  const { data: events = [], isLoading, refetch } = useQuery<AuditEvent[]>({
    queryKey: ['audit', filterType, filterSymbol, filterSource, filterClass],
    queryFn: () => fetchAuditEvents(params),
    refetchInterval: 15000,
  })

  const { data: typesData } = useQuery<{ event_types: string[] }>({
    queryKey: ['audit-event-types'],
    queryFn: fetchEventTypes,
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Audit Trail</h1>
          <p className="text-sm text-gray-500 mt-1">{events.length} events</p>
        </div>
        <div className="flex gap-3">
          <button onClick={() => setFiltersOpen(o => !o)} className="btn-ghost flex items-center gap-1.5">
            <Filter size={14} />
            Filters
          </button>
          <button onClick={() => refetch()} className="btn-ghost flex items-center gap-1.5">
            <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </div>

      {filtersOpen && (
        <div className="card flex flex-wrap gap-4">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-gray-500">Event Type</label>
            <select
              value={filterType}
              onChange={e => setFilterType(e.target.value)}
              className="bg-surface border border-surface-border rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-brand"
            >
              <option value="">All</option>
              {typesData?.event_types.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-gray-500">Symbol</label>
            <input
              type="text"
              value={filterSymbol}
              onChange={e => setFilterSymbol(e.target.value)}
              placeholder="e.g. XBTUSD"
              className="bg-surface border border-surface-border rounded-lg px-3 py-2 text-sm mono text-white focus:outline-none focus:border-brand w-36"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-gray-500">Source</label>
            <select
              value={filterSource}
              onChange={e => setFilterSource(e.target.value)}
              className="bg-surface border border-surface-border rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-brand"
            >
              <option value="">All</option>
              {['SYSTEM', 'DISCORD', 'USER', 'BROKER', 'WORKER'].map(s =>
                <option key={s} value={s}>{s}</option>
              )}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-gray-500">Asset Class</label>
            <select
              value={filterClass}
              onChange={e => setFilterClass(e.target.value)}
              className="bg-surface border border-surface-border rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-brand"
            >
              <option value="">All</option>
              <option value="crypto">Crypto</option>
              <option value="stock">Stock</option>
            </select>
          </div>
          <button
            onClick={() => { setFilterType(''); setFilterSymbol(''); setFilterSource(''); setFilterClass('') }}
            className="btn-ghost self-end"
          >
            Clear
          </button>
        </div>
      )}

      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-surface-border text-xs text-gray-500 uppercase tracking-wider">
              <th className="text-left px-5 py-3">Time</th>
              <th className="text-left px-5 py-3">Event</th>
              <th className="text-left px-5 py-3">Symbol</th>
              <th className="text-left px-5 py-3">Source</th>
              <th className="text-left px-5 py-3">Message</th>
              <th className="px-5 py-3" />
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr><td colSpan={6} className="px-5 py-8 text-center text-gray-500">Loading…</td></tr>
            )}
            {!isLoading && events.length === 0 && (
              <tr><td colSpan={6} className="px-5 py-8 text-center text-gray-500">No events</td></tr>
            )}
            {events.map(ev => {
              const isExp = expanded === ev.id
              return (
                <>
                  <tr
                    key={ev.id}
                    className="border-b border-surface-border/50 table-row-hover cursor-pointer"
                    onClick={() => setExpanded(isExp ? null : ev.id)}
                  >
                    <td className="px-5 py-3 text-gray-500 text-xs whitespace-nowrap">
                      {ev.created_at
                        ? <span title={relativeTime(ev.created_at)}>
                            {formatET(ev.created_at)}
                          </span>
                        : '—'}
                    </td>
                    <td className={clsx('px-5 py-3 text-xs font-medium mono', eventTypeColors[ev.event_type] || 'text-gray-300')}>
                      {ev.event_type}
                    </td>
                    <td className="px-5 py-3 mono text-white text-sm">
                      {ev.symbol
                        ? <span className="flex items-center gap-1.5">
                            {ev.symbol}
                            {ev.asset_class && (
                              <span className={`badge text-[10px] ${ev.asset_class === 'crypto' ? 'bg-violet-500/20 text-violet-400 border border-violet-500/30' : 'bg-sky-500/20 text-sky-400 border border-sky-500/30'}`}>
                                {ev.asset_class}
                              </span>
                            )}
                          </span>
                        : <span className="text-gray-600">—</span>}
                    </td>
                    <td className="px-5 py-3">
                      <span className={clsx('badge', sourceColors[ev.source] || 'bg-gray-500/20 text-gray-400')}>
                        {ev.source}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-gray-400 text-xs max-w-xs truncate">{ev.message || '—'}</td>
                    <td className="px-5 py-3 text-gray-600 text-xs">
                      {ev.event_data && Object.keys(ev.event_data).length > 0 ? '▸' : ''}
                    </td>
                  </tr>
                  {isExp && ev.event_data && (
                    <tr key={ev.id + '-data'} className="border-b border-surface-border bg-surface/60">
                      <td colSpan={6} className="px-5 py-3">
                        <pre className="text-xs mono text-gray-400 overflow-auto max-h-40">
                          {JSON.stringify(ev.event_data, null, 2)}
                        </pre>
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
