import { useState, useMemo, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  useReactTable,
  SortingState,
} from '@tanstack/react-table'
import { fetchMonitoringCandidates, evaluateSymbol } from '@/api/endpoints'
import StatusBadge from '@/components/StatusBadge'
import { RefreshCw, Search, Activity, Crosshair, TerminalSquare, ArrowUpDown, ChevronRight, Zap } from 'lucide-react'
import clsx from 'clsx'

interface Candidate {
  symbol: string
  asset_class: string
  state: string
  added_at: string | null
  watchlist_source_id: string | null
  top_strategy: string | null
  top_confidence: number | null
  top_entry: number | null
  blocked_reason?: string | null
  has_open_position?: boolean
  cooldown_active?: boolean
  regime_allowed?: boolean | null
  evaluation_error?: string | null
  top_notes?: string | null
  position_or_order_status?: string | null
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

const columnHelper = createColumnHelper()

export default function Monitoring() {
  const [filterClass, setFilterClass] = useState<string>('')
  const [globalFilter, setGlobalFilter] = useState('')
  const [sorting, setSorting] = useState<any>([{ id: 'top_confidence', desc: true }])
  
  const [evalSymbol, setEvalSymbol] = useState('')
  const [evalClass, setEvalClass] = useState<'crypto' | 'stock'>('crypto')
  const [evalResult, setEvalResult] = useState<EvalResult | null>(null)
  const [evalLoading, setEvalLoading] = useState(false)

  const params: Record<string, string> = {}
  if (filterClass) params.asset_class = filterClass

  const q = useQuery({
    queryKey: ['monitoring', filterClass],
    queryFn: () => fetchMonitoringCandidates(params),
    refetchInterval: 30000,
  }) as { data?: { candidates: Candidate[]; total: number }; isLoading?: boolean; isRefetching?: boolean; refetch?: () => Promise<any> }
  const data = q.data
  const isLoading = q.isLoading
  const isRefetching = q.isRefetching
  const refetch = q.refetch

  const strongestCandidates = useMemo(() => {
    const rows = data?.candidates ?? []
    const bestBySymbol = new Map<string, Candidate>()

    for (const row of rows) {
      const key = row.symbol?.toUpperCase() ?? ''
      const current = bestBySymbol.get(key)

      if (!current) {
        bestBySymbol.set(key, row)
        continue
      }

      const currentConfidence = current.top_confidence ?? Number.NEGATIVE_INFINITY
      const nextConfidence = row.top_confidence ?? Number.NEGATIVE_INFINITY

      if (nextConfidence > currentConfidence) {
        bestBySymbol.set(key, row)
        continue
      }

      if (nextConfidence === currentConfidence) {
        const currentAddedAt = current.added_at ? new Date(current.added_at).getTime() : Number.NEGATIVE_INFINITY
        const nextAddedAt = row.added_at ? new Date(row.added_at).getTime() : Number.NEGATIVE_INFINITY
        if (nextAddedAt > currentAddedAt) {
          bestBySymbol.set(key, row)
        }
      }
    }

    return Array.from(bestBySymbol.values())
  }, [data?.candidates])

  const handleEvaluate = useCallback(async (targetSymbol?: string, targetClass?: 'crypto' | 'stock') => {
    const sym = targetSymbol || evalSymbol
    const cls = targetClass || evalClass

    if (!sym.trim()) return

    setEvalSymbol(sym.toUpperCase())
    setEvalClass(cls)
    setEvalLoading(true)
    setEvalResult(null)

    try {
      const result = await evaluateSymbol(sym.trim().toUpperCase(), cls)
      setEvalResult(result)
    } catch {
      setEvalResult({ symbol: sym, asset_class: cls, signals: [], error: 'Uplink to analysis engine failed.' })
    } finally {
      setEvalLoading(false)
    }
  }, [evalSymbol, evalClass])

  const columns = useMemo(() => [
    columnHelper.accessor('symbol', {
      header: 'TARGET_VECTOR',
      cell: info => (
        <div className="flex items-center gap-2">
          <div className={clsx(
            "w-1.5 h-1.5 rounded-full shadow-[0_0_5px_currentColor]",
            info.row.original.asset_class === 'crypto' ? 'text-[#5865F2] bg-[#5865F2]' : 'text-system-online bg-system-online'
          )}></div>
          <span className="font-bold tracking-wider text-white">{info.getValue()}</span>
        </div>
      ),
    }),
    columnHelper.display({
      id: 'diagnostics',
      header: 'DIAG',
      cell: info => {
        const row = info.row.original
        const parts: string[] = []
        if (row.evaluation_error) parts.push('ERR')
        if (row.has_open_position) parts.push('OPEN_POS')
        if (row.cooldown_active) parts.push('COOLDOWN')
        if (row.regime_allowed === false) parts.push('REGIME_BLOCK')
        if (row.blocked_reason) parts.push('BLOCKED')
        return (
          <div className="text-[10px] mono text-gray-400">
            {parts.length === 0 ? <span className="text-system-online">READY</span> : parts.join(' • ')}
          </div>
        )
      }
    }),
    columnHelper.accessor('asset_class', {
      header: 'NODE',
      cell: info => <span className="text-xs text-gray-400 uppercase tracking-widest">{info.getValue()}</span>
    }),
    columnHelper.accessor('state', {
      header: 'SYS_STATE',
      cell: info => {
        const raw = info.getValue()
        return <StatusBadge status={raw} showRaw />
      },
    }),
    columnHelper.accessor('top_strategy', {
      header: 'PRIMARY_ALGO',
      cell: info => {
        const val = info.getValue()
        if (!val) return <span className="text-gray-600 mono text-xs">—</span>
        return <span className="text-xs font-mono font-medium text-gray-300 uppercase tracking-wider bg-surface-card border border-surface-border px-2 py-0.5 rounded">{val}</span>
      }
    }),
    columnHelper.accessor('top_confidence', {
      header: 'CONFIDENCE',
      cell: info => {
        const val = info.getValue()
        if (val == null) return <span className="text-gray-600 mono text-xs">—</span>
        return (
          <span className={clsx(
            "mono font-bold drop-shadow-[0_0_5px_currentColor]",
            val >= 0.8 ? "text-system-online" : val >= 0.5 ? "text-brand" : "text-system-warning"
          )}>
            {(val * 100).toFixed(0)}%
          </span>
        )
      }
    }),
    columnHelper.accessor('added_at', {
      header: 'TRACKING_SINCE',
      cell: info => {
        const val = info.getValue()
        return <span className="text-xs text-gray-400 mono">{val ? new Date(val).toLocaleDateString() : '—'}</span>
      }
    }),
    columnHelper.display({
      id: 'actions',
      header: 'OPERATIONS',
      cell: info => (
        <button
          onClick={() => handleEvaluate(info.row.original.symbol, info.row.original.asset_class as 'crypto' | 'stock')}
          className="text-xs font-mono font-bold tracking-widest uppercase text-brand hover:text-white transition-colors flex items-center gap-1 bg-brand/10 hover:bg-brand/20 border border-brand/30 px-2 py-1 rounded"
        >
          Ping <ChevronRight size={12} />
        </button>
      )
    })
  ], [handleEvaluate])

  const table = useReactTable({
    data: strongestCandidates,
    columns,
    state: { sorting, globalFilter },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  })

  return (
    <div className="space-y-6 max-w-[1600px] mx-auto pb-10 h-full flex flex-col">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 border-b border-surface-border pb-4 shrink-0">
        <div>
          <h1 className="text-3xl font-bold text-white tracking-tight flex items-center gap-3">
            <Activity className="text-brand" /> 
            Live Telemetry
          </h1>
          <div className="flex items-center gap-3 mt-2 mono text-xs text-gray-500">
            <span>ACTIVE_CANDIDATES: <span className="text-white">{strongestCandidates.length}</span></span>
            <span>|</span>
            <span className="text-system-online animate-pulse">MONITORING_NODES_ONLINE</span>
          </div>
        </div>
        
        <div className="flex items-center gap-3">
          <div className="relative group hidden md:block">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 group-focus-within:text-brand transition-colors" />
            <input
              type="text"
              value={globalFilter ?? ''}
              onChange={e => setGlobalFilter(e.target.value)}
              placeholder="Search telemetry..."
              className="bg-[#12141f] border border-surface-border rounded-lg py-1.5 pl-9 pr-4 text-white font-mono text-sm focus:outline-none focus:border-brand/50 focus:ring-1 focus:ring-brand/50 w-48 transition-all"
            />
          </div>
          <div className="w-[1px] h-6 bg-surface-border"></div>
          <button onClick={() => refetch()} className="btn-ghost flex items-center gap-2 px-3">
            <RefreshCw size={14} className={isLoading || isRefetching ? 'animate-spin text-brand' : ''} />
            <span className="mono text-xs uppercase tracking-wider">Sync Telemetry</span>
          </button>
        </div>
      </div>

      {/* On-Demand Analysis Console */}
      <div className="card space-y-4 bg-[#0d0f18] shrink-0 border-brand/20 shadow-card-inset">
        <div className="flex flex-col md:flex-row md:items-end gap-4">
          <div className="flex-1 space-y-3">
            <div className="text-xs text-brand mono font-bold uppercase tracking-widest flex items-center gap-2">
              <TerminalSquare size={14} /> On-Demand Telemetry Ping
            </div>
            <div className="flex gap-3 flex-wrap">
              <div className="relative">
                <Crosshair size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
                <input
                  type="text"
                  placeholder="Target (e.g. XBTUSD)"
                  value={evalSymbol}
                  onChange={e => setEvalSymbol(e.target.value.toUpperCase())}
                  onKeyDown={e => e.key === 'Enter' && handleEvaluate()}
                  className="bg-[#12141f] border border-surface-border rounded-lg pl-9 pr-4 py-2 text-sm text-white focus:outline-none focus:border-brand focus:ring-1 focus:ring-brand mono w-56 transition-all uppercase"
                  spellCheck="false"
                />
              </div>
              <select
                value={evalClass}
                onChange={e => setEvalClass(e.target.value as 'crypto' | 'stock')}
                className="bg-[#12141f] border border-surface-border rounded-lg px-4 py-2 text-sm text-white font-mono focus:outline-none focus:border-brand focus:ring-1 focus:ring-brand transition-all uppercase tracking-widest"
              >
                <option value="crypto">Node_A (Crypto)</option>
                <option value="stock">Node_B (Stock)</option>
              </select>
              <button
                onClick={() => handleEvaluate()}
                disabled={evalLoading || !evalSymbol.trim()}
                className="btn-primary flex items-center gap-2 px-6"
              >
                {evalLoading ? <Activity size={14} className="animate-pulse" /> : <Zap size={14} />}
                <span className="mono font-bold tracking-widest uppercase text-xs">Execute Ping</span>
              </button>
            </div>
          </div>
        </div>

        {/* Evaluation Results Render */}
        {evalResult && (
          <div className="pt-4 border-t border-surface-border animate-in fade-in slide-in-from-top-2 duration-300">
            {evalResult.error && (
              <div className="bg-system-offline/10 border border-system-offline/30 text-system-offline mono text-xs p-3 rounded uppercase tracking-widest flex items-center gap-2 shadow-card-inset">
                <Activity size={14} /> [ERR] {evalResult.error}
              </div>
            )}
            
            {evalResult.signals.length === 0 && !evalResult.error && (
              <div className="bg-surface-card border border-surface-border text-gray-400 mono text-xs p-3 rounded uppercase tracking-widest flex items-center gap-2 shadow-card-inset">
                <Crosshair size={14} /> Target {evalResult.symbol} scanned. No valid entry vectors identified.
              </div>
            )}

            {evalResult.signals.length > 0 && (
              <div className="space-y-3">
                <div className="text-[10px] text-gray-500 mono uppercase tracking-widest">Valid Vectors Identified ({evalResult.signals.length})</div>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  {evalResult.signals.map((sig, i) => (
                    <div key={i} className="bg-[#12141f] rounded-lg border border-system-online/30 p-4 space-y-3 shadow-[inset_0_0_20px_rgba(16,185,129,0.05),0_0_15px_-5px_rgba(16,185,129,0.15)] relative overflow-hidden group">
                      <div className="absolute top-0 left-0 w-1 h-full bg-system-online shadow-[0_0_10px_rgba(16,185,129,0.8)]"></div>
                      
                      <div className="flex items-center justify-between pl-2">
                        <span className="font-bold text-white font-mono uppercase tracking-widest text-sm flex items-center gap-2">
                          <Zap size={14} className="text-system-online" /> {sig.strategy}
                        </span>
                        <span className="text-xs mono font-bold text-system-online border border-system-online/30 bg-system-online/10 px-2 py-0.5 rounded">
                          {(sig.confidence * 100).toFixed(0)}% CONF
                        </span>
                      </div>

                      <div className="grid grid-cols-4 gap-2 pl-2 border-t border-surface-border/50 pt-3">
                        <MetricBlock label="ENTRY" value={sig.entry_price} color="text-white" />
                        <MetricBlock label="STOP" value={sig.stop} color="text-system-offline drop-shadow-[0_0_5px_rgba(239,68,68,0.5)]" />
                        <MetricBlock label="TGT_1" value={sig.tp1} color="text-system-online drop-shadow-[0_0_5px_rgba(16,185,129,0.5)]" />
                        <MetricBlock label="TGT_2" value={sig.tp2} color="text-system-online drop-shadow-[0_0_5px_rgba(16,185,129,0.5)]" />
                      </div>

                      <div className="bg-surface border border-surface-border rounded p-2 pl-3 ml-2 text-[10px] mono text-gray-400 mt-2">
                        <span className="text-brand font-bold mr-2">[{sig.regime}]</span>
                        {sig.notes}
                      </div>
                      {/* Diagnostic area: if server returned extra diagnostics, show them */}
                      {evalResult && evalResult.signals && evalResult.signals.length > 0 && (
                        <div className="mt-2 text-[12px] text-gray-400 mono flex flex-col gap-1">
                          {/* Top notes from monitoring candidate shown when available */}
                          {evalResult && evalResult.signals && evalResult.signals[0] && evalResult.signals[0].notes && (
                            <div>ANALYSIS_NOTES: <span className="text-white ml-1">{evalResult.signals[0].notes}</span></div>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Target Data Grid */}
      <div className="flex items-center justify-between px-1">
        <div className="text-xs text-gray-500 mono font-bold uppercase tracking-widest">Active Scan Array</div>
        <div className="flex gap-2 bg-[#12141f] p-1 rounded-lg border border-surface-border">
          {['', 'crypto', 'stock'].map(c => (
            <button
              key={c}
              onClick={() => setFilterClass(c)}
              className={clsx(
                "px-4 py-1.5 rounded-md text-[10px] font-mono uppercase tracking-widest transition-all",
                filterClass === c 
                  ? "bg-brand/20 text-brand font-bold border border-brand/30 shadow-[0_0_10px_rgba(99,102,241,0.2)]" 
                  : "text-gray-500 hover:text-gray-300 border border-transparent"
              )}
            >
              {c || 'ALL_NODES'}
            </button>
          ))}
        </div>
      </div>

      <div className="card p-0 flex-1 flex flex-col overflow-hidden border border-surface-border bg-surface-card/40 backdrop-blur-sm relative shadow-card-inset">
        {isLoading ? (
          <div className="flex-1 flex flex-col items-center justify-center text-gray-500 gap-3 min-h-[300px]">
             <Activity className="animate-pulse-slow text-brand" size={32} />
             <span className="mono text-xs uppercase tracking-widest">Polling Telemetry Nodes...</span>
          </div>
        ) : strongestCandidates.length === 0 ? (
          <div className="flex-1 flex items-center justify-center text-gray-500 mono text-sm uppercase tracking-widest min-h-[300px]">
            No Telemetry Data Available
          </div>
        ) : (
          <div className="overflow-auto flex-1 scrollbar-thin">
            <table className="w-full text-left border-collapse">
              <thead className="sticky top-0 z-20 bg-[#0b0c13] border-b border-surface-border">
                {table.getHeaderGroups().map(headerGroup => (
                  <tr key={headerGroup.id}>
                    {headerGroup.headers.map(header => (
                      <th 
                        key={header.id} 
                        onClick={header.column.getToggleSortingHandler()}
                        className={clsx(
                          "py-3 px-5 text-[10px] font-mono font-bold uppercase tracking-widest text-gray-500 bg-surface-card/80 backdrop-blur-md select-none whitespace-nowrap",
                          header.column.getCanSort() ? "cursor-pointer hover:text-white transition-colors group" : ""
                        )}
                      >
                        <div className="flex items-center gap-2">
                          {flexRender(header.column.columnDef.header, header.getContext())}
                          {header.column.getCanSort() && (
                            <ArrowUpDown size={12} className={clsx(
                              "transition-opacity",
                              header.column.getIsSorted() ? "opacity-100 text-brand" : "opacity-0 group-hover:opacity-50"
                            )} />
                          )}
                        </div>
                      </th>
                    ))}
                  </tr>
                ))}
              </thead>
              <tbody className="mono text-sm">
                {table.getRowModel().rows.map(row => (
                  <tr key={row.id} className="border-b border-surface-border/30 hover:bg-white/[0.02] transition-colors group">
                    {row.getVisibleCells().map(cell => (
                      <td key={cell.id} className="py-2.5 px-5 whitespace-nowrap">
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="bg-[#0b0c13] border-t border-surface-border px-5 py-2 flex justify-between items-center text-[10px] mono text-gray-600 uppercase tracking-widest shrink-0">
          <span>{table.getRowModel().rows.length} Rendered</span>
          <span>Buffer: <span className="text-system-online">Synced</span></span>
        </div>
      </div>
    </div>
  )
}

function MetricBlock({ label, value, color }: { label: string, value: number, color: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-[9px] text-gray-500 mono mb-0.5">{label}</span>
      <span className={clsx("font-mono font-bold text-sm tracking-tight", color)}>
        {value.toFixed(4)}
      </span>
    </div>
  )
}