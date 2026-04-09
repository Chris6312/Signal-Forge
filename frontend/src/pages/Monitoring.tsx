import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchMonitoringCandidates, evaluateSymbol } from '@/api/endpoints'
import StatusBadge from '@/components/StatusBadge'
import { RefreshCw, Search, ChevronRight } from 'lucide-react'

interface Candidate {
  symbol: string
  asset_class: string
  state: string
  added_at: string | null
  watchlist_source_id: string | null
  top_strategy: string | null
  top_confidence: number | null
  top_entry: number | null
}

interface Signal {
  strategy: string
  entry_price: number
  stop: number
  tp1: number
  tp2: number
  regime: string
  confidence: number
  notes: string
}

interface EvalResult {
  symbol: string
  asset_class: string
  signals: Signal[]
  error?: string
}

export default function Monitoring() {
  const [filterClass, setFilterClass] = useState<string>('')
  const [evalSymbol, setEvalSymbol] = useState('')
  const [evalClass, setEvalClass] = useState<'crypto' | 'stock'>('crypto')
  const [evalResult, setEvalResult] = useState<EvalResult | null>(null)
  const [evalLoading, setEvalLoading] = useState(false)

  const params: Record<string, string> = {}
  if (filterClass) params.asset_class = filterClass

  const { data, isLoading, refetch } = useQuery<{ candidates: Candidate[]; total: number }>({
    queryKey: ['monitoring', filterClass],
    queryFn: () => fetchMonitoringCandidates(params),
    refetchInterval: 30000,
  })

  const handleEvaluate = async () => {
    if (!evalSymbol.trim()) return
    setEvalLoading(true)
    setEvalResult(null)
    try {
      const result = await evaluateSymbol(evalSymbol.trim().toUpperCase(), evalClass)
      setEvalResult(result)
    } catch {
      setEvalResult({ symbol: evalSymbol, asset_class: evalClass, signals: [], error: 'Request failed' })
    } finally {
      setEvalLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Monitoring</h1>
          <p className="text-sm text-gray-500 mt-1">
            {data?.total ?? 0} candidates in active watchlist
          </p>
        </div>
        <button onClick={() => refetch()} className="btn-ghost flex items-center gap-1.5">
          <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {/* Filter */}
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

      {/* Candidates */}
      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-surface-border text-xs text-gray-500 uppercase tracking-wider">
              <th className="text-left px-5 py-3">Symbol</th>
              <th className="text-left px-5 py-3">Asset Class</th>
              <th className="text-left px-5 py-3">State</th>
              <th className="text-left px-5 py-3">Top Strategy</th>
              <th className="text-left px-5 py-3">Added</th>
              <th className="px-5 py-3" />
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr><td colSpan={6} className="px-5 py-8 text-center text-gray-500">Loading…</td></tr>
            )}
            {!isLoading && !data?.candidates.length && (
              <tr><td colSpan={6} className="px-5 py-8 text-center text-gray-500">No active candidates</td></tr>
            )}
            {data?.candidates.map(c => (
              <tr key={c.symbol + c.asset_class} className="border-b border-surface-border/50 table-row-hover">
                <td className="px-5 py-3 mono font-medium text-white">{c.symbol}</td>
                <td className="px-5 py-3">
                  <span className={`badge ${c.asset_class === 'crypto' ? 'bg-violet-500/20 text-violet-400 border border-violet-500/30' : 'bg-sky-500/20 text-sky-400 border border-sky-500/30'}`}>
                    {c.asset_class}
                  </span>
                </td>
                <td className="px-5 py-3"><StatusBadge status={c.state} /></td>
                <td className="px-5 py-3">
                  {c.top_strategy ? (
                    <div>
                      <div className="text-xs font-medium text-white">{c.top_strategy}</div>
                      <div className="text-xs mono text-brand">
                        {c.top_confidence != null ? `${(c.top_confidence * 100).toFixed(0)}% conf` : ''}
                      </div>
                    </div>
                  ) : (
                    <span className="text-gray-500 text-xs">—</span>
                  )}
                </td>
                <td className="px-5 py-3 text-gray-400 text-xs">{c.added_at ? new Date(c.added_at).toLocaleDateString() : '—'}</td>
                <td className="px-5 py-3">
                  <button
                    onClick={() => { setEvalSymbol(c.symbol); setEvalClass(c.asset_class as 'crypto' | 'stock') }}
                    className="text-brand hover:text-brand-dark flex items-center gap-1 text-xs"
                  >
                    Evaluate <ChevronRight size={12} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Manual evaluation */}
      <div className="card space-y-4">
        <div className="text-sm font-medium text-gray-300">On-Demand Strategy Evaluation</div>
        <div className="flex gap-3 flex-wrap">
          <input
            type="text"
            placeholder="Symbol (e.g. XBTUSD)"
            value={evalSymbol}
            onChange={e => setEvalSymbol(e.target.value.toUpperCase())}
            onKeyDown={e => e.key === 'Enter' && handleEvaluate()}
            className="bg-surface border border-surface-border rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-brand mono w-48"
          />
          <select
            value={evalClass}
            onChange={e => setEvalClass(e.target.value as 'crypto' | 'stock')}
            className="bg-surface border border-surface-border rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-brand"
          >
            <option value="crypto">Crypto</option>
            <option value="stock">Stock</option>
          </select>
          <button
            onClick={handleEvaluate}
            disabled={evalLoading}
            className="btn-primary flex items-center gap-2"
          >
            <Search size={14} />
            {evalLoading ? 'Evaluating…' : 'Evaluate'}
          </button>
        </div>

        {evalResult && (
          <div className="space-y-3">
            {evalResult.error && (
              <div className="text-red-400 text-sm">{evalResult.error}</div>
            )}
            {evalResult.signals.length === 0 && !evalResult.error && (
              <div className="text-gray-500 text-sm">No entry signals found for {evalResult.symbol}</div>
            )}
            {evalResult.signals.map((sig, i) => (
              <div key={i} className="bg-surface rounded-lg border border-surface-border p-4 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-white text-sm">{sig.strategy}</span>
                  <span className="text-xs mono text-brand">{(sig.confidence * 100).toFixed(0)}% confidence</span>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                  <div><span className="text-gray-500">Entry</span><div className="mono text-white">{sig.entry_price?.toFixed(4)}</div></div>
                  <div><span className="text-gray-500">Stop</span><div className="mono text-red-400">{sig.stop?.toFixed(4)}</div></div>
                  <div><span className="text-gray-500">TP1</span><div className="mono text-emerald-400">{sig.tp1?.toFixed(4)}</div></div>
                  <div><span className="text-gray-500">TP2</span><div className="mono text-emerald-400">{sig.tp2?.toFixed(4)}</div></div>
                </div>
                <div className="text-xs text-gray-500">Regime: <span className="text-gray-300">{sig.regime}</span> · {sig.notes}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
