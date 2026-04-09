import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchWatchlist, postWatchlistUpdate } from '@/api/endpoints'
import StatusBadge from '@/components/StatusBadge'
import { RefreshCw, Plus, ChevronDown, ChevronUp } from 'lucide-react'
import { formatET, relativeTime } from '@/utils/time'

interface WatchlistSymbol {
  id: string
  symbol: string
  asset_class: string
  state: string
  watchlist_source_id: string | null
  added_at: string | null
  removed_at: string | null
  managed_since: string | null
}

const EXAMPLE_PAYLOAD = JSON.stringify(
  {
    watchlist: [
      { symbol: 'XBTUSD', asset_class: 'crypto' },
      { symbol: 'ETHUSD', asset_class: 'crypto' },
      { symbol: 'AAPL', asset_class: 'stock' },
      { symbol: 'TSLA', asset_class: 'stock' },
    ],
  },
  null,
  2,
)

export default function Watchlist() {
  const qc = useQueryClient()
  const [filterState, setFilterState] = useState<string>('')
  const [filterClass, setFilterClass] = useState<string>('')
  const [jsonInput, setJsonInput] = useState(EXAMPLE_PAYLOAD)
  const [jsonOpen, setJsonOpen] = useState(false)
  const [updateResult, setUpdateResult] = useState<string | null>(null)

  const params: Record<string, string> = {}
  if (filterState) params.state = filterState
  if (filterClass) params.asset_class = filterClass

  const { data = [], isLoading, refetch } = useQuery<WatchlistSymbol[]>({
    queryKey: ['watchlist', filterState, filterClass],
    queryFn: () => fetchWatchlist(params),
    refetchInterval: 15000,
  })

  const mutation = useMutation({
    mutationFn: (body: { watchlist: object[]; source_id: string }) => postWatchlistUpdate(body),
    onSuccess: (result) => {
      setUpdateResult(JSON.stringify(result, null, 2))
      qc.invalidateQueries({ queryKey: ['watchlist'] })
    },
  })

  const handleSubmit = () => {
    try {
      const parsed = JSON.parse(jsonInput)
      mutation.mutate({ watchlist: parsed.watchlist, source_id: 'manual' })
    } catch {
      setUpdateResult('Error: invalid JSON')
    }
  }

  const active = data.filter(s => s.state === 'ACTIVE')
  const managed = data.filter(s => s.state === 'MANAGED')

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Watchlist</h1>
          <p className="text-sm text-gray-500 mt-1">
            {active.length} active · {managed.length} managed
          </p>
        </div>
        <button onClick={() => refetch()} className="btn-ghost flex items-center gap-1.5">
          <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {/* Filters */}
      <div className="flex gap-3 flex-wrap">
        {['', 'ACTIVE', 'MANAGED'].map(s => (
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

      {/* Symbol table */}
      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-surface-border text-xs text-gray-500 uppercase tracking-wider">
              <th className="text-left px-5 py-3">Symbol</th>
              <th className="text-left px-5 py-3">Class</th>
              <th className="text-left px-5 py-3">State</th>
              <th className="text-left px-5 py-3">Source ID</th>
              <th className="text-left px-5 py-3">Added</th>
              <th className="text-left px-5 py-3">Managed Since</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td colSpan={6} className="px-5 py-8 text-center text-gray-500">Loading…</td>
              </tr>
            )}
            {!isLoading && data.length === 0 && (
              <tr>
                <td colSpan={6} className="px-5 py-8 text-center text-gray-500">No symbols found</td>
              </tr>
            )}
            {data.map(sym => (
              <tr key={sym.id} className="border-b border-surface-border/50 table-row-hover">
                <td className="px-5 py-3 font-medium mono text-white">{sym.symbol}</td>
                <td className="px-5 py-3">
                  <span className={`badge ${sym.asset_class === 'crypto' ? 'bg-violet-500/20 text-violet-400 border border-violet-500/30' : 'bg-sky-500/20 text-sky-400 border border-sky-500/30'}`}>
                    {sym.asset_class}
                  </span>
                </td>
                <td className="px-5 py-3"><StatusBadge status={sym.state} /></td>
                <td className="px-5 py-3 text-gray-500 mono text-xs">{sym.watchlist_source_id || '—'}</td>
                <td className="px-5 py-3 text-gray-400 text-xs whitespace-nowrap">
                  {sym.added_at
                    ? <span title={relativeTime(sym.added_at)}>{formatET(sym.added_at)}</span>
                    : '—'}
                </td>
                <td className="px-5 py-3 text-gray-400 text-xs whitespace-nowrap">
                  {sym.managed_since
                    ? <span title={relativeTime(sym.managed_since)}>{formatET(sym.managed_since)}</span>
                    : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Manual update */}
      <div className="card space-y-4">
        <button
          className="flex items-center gap-2 w-full text-sm font-medium text-gray-300"
          onClick={() => setJsonOpen(o => !o)}
        >
          <Plus size={14} className="text-brand" />
          Manual Watchlist Update
          {jsonOpen ? <ChevronUp size={14} className="ml-auto" /> : <ChevronDown size={14} className="ml-auto" />}
        </button>

        {jsonOpen && (
          <div className="space-y-3">
            <p className="text-xs text-gray-500">
              Paste the AI-generated watchlist JSON below and click Submit.
            </p>
            <textarea
              className="w-full bg-surface border border-surface-border rounded-lg p-3 text-sm mono text-gray-300 focus:outline-none focus:border-brand resize-none"
              rows={10}
              value={jsonInput}
              onChange={e => setJsonInput(e.target.value)}
            />
            <div className="flex gap-3">
              <button onClick={handleSubmit} className="btn-primary" disabled={mutation.isPending}>
                {mutation.isPending ? 'Submitting…' : 'Submit Watchlist'}
              </button>
              {updateResult && (
                <button onClick={() => setUpdateResult(null)} className="btn-ghost text-xs">
                  Clear result
                </button>
              )}
            </div>
            {updateResult && (
              <pre className="bg-surface rounded-lg p-3 text-xs mono text-gray-300 overflow-auto max-h-48">
                {updateResult}
              </pre>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
