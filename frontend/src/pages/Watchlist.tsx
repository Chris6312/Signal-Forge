import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  useReactTable,
  SortingState,
} from '@tanstack/react-table'
import { fetchWatchlist, postWatchlistUpdate } from '@/api/endpoints'
import StatusBadge from '@/components/StatusBadge'
import { RefreshCw, Search, Crosshair, TerminalSquare, Activity, ArrowUpDown } from 'lucide-react'
import { formatET, relativeTime } from '@/utils/time'
import clsx from 'clsx'

interface WatchlistSymbol {
  id: string
  symbol: string
  asset_class: string
  state: string
  watchlist_source_id: string | null
  added_at: string | null
  removed_at: string | null
  managed_since: string | null
  reason?: string | null
  confidence?: number | null
  tags?: string[] | null
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

const columnHelper = createColumnHelper<WatchlistSymbol>()

export default function Watchlist() {
  const qc = useQueryClient()
  const [filterState, setFilterState] = useState<string>('')
  const [filterClass, setFilterClass] = useState<string>('')
  const [globalFilter, setGlobalFilter] = useState('')
  const [sorting, setSorting] = useState<SortingState>([{ id: 'added_at', desc: true }])
  const [tagFilter, setTagFilter] = useState<string>('')
  const [confidenceSort, setConfidenceSort] = useState<'none' | 'asc' | 'desc'>('none')
  
  const [jsonInput, setJsonInput] = useState(EXAMPLE_PAYLOAD)
  const [jsonOpen, setJsonOpen] = useState(false)
  const [updateResult, setUpdateResult] = useState<string | null>(null)

  const params: Record<string, string> = {}
  if (filterState) params.state = filterState
  if (filterClass) params.asset_class = filterClass

  const { data = [], isLoading, isRefetching, refetch } = useQuery<WatchlistSymbol[]>({
    queryKey: ['watchlist', filterState, filterClass],
    queryFn: () => fetchWatchlist(params),
    refetchInterval: 15000,
  })

  const mutation = useMutation({
    mutationFn: (body: { watchlist: object[]; source_id: string }) => postWatchlistUpdate(body),
    onSuccess: (result) => {
      setUpdateResult(`[SYS_SUCCESS] Payload accepted. \n${JSON.stringify(result, null, 2)}`)
      qc.invalidateQueries({ queryKey: ['watchlist'] })
    },
    onError: (error: any) => {
      setUpdateResult(`[SYS_ERROR] Rejection: ${error.message}`)
    }
  })

  const handleSubmit = () => {
    try {
      const parsed = JSON.parse(jsonInput)
      mutation.mutate({ watchlist: parsed.watchlist, source_id: 'manual' })
    } catch {
      setUpdateResult('[SYS_ERROR] Invalid JSON payload sequence.')
    }
  }

  const columns = useMemo(() => [
    columnHelper.accessor('symbol', {
      header: 'RADAR_TARGET',
      cell: info => (
        <div className="flex items-center gap-2">
          <div className={clsx(
            "w-1.5 h-1.5 rounded-full shadow-[0_0_5px_currentColor]",
            info.row.original.asset_class === 'crypto' ? 'text-[#5865F2] bg-[#5865F2]' : 'text-system-online bg-system-online'
          )}></div>
          <span className="font-bold tracking-wider text-white text-sm">{info.getValue()}</span>
        </div>
      ),
    }),
    columnHelper.accessor('state', {
      header: 'STATUS',
      cell: info => <StatusBadge status={info.getValue()} />,
    }),
    columnHelper.accessor('asset_class', {
      header: 'NODE',
      cell: info => <span className="text-xs text-gray-400 uppercase tracking-widest">{info.getValue()}</span>
    }),
    columnHelper.accessor('watchlist_source_id', {
      header: 'ORIGIN_ID',
      cell: info => <span className="text-[10px] text-gray-500 font-mono bg-surface-card border border-surface-border px-1.5 py-0.5 rounded">{info.getValue() || 'MANUAL'}</span>,
    }),
    columnHelper.accessor('reason', {
      header: 'REASON',
      cell: info => <span className="text-[12px] text-gray-300 max-w-[280px] truncate inline-block">{info.getValue() || '—'}</span>,
    }),
    columnHelper.accessor('confidence', {
      header: 'CONF',
      cell: info => {
        const v = info.getValue()
        return v == null ? <span className="text-gray-500">—</span> : <span className="text-xs font-mono text-white">{(v as number).toFixed(2)}</span>
      }
    }),
    columnHelper.accessor('tags', {
      header: 'TAGS',
      cell: info => {
        const tags = info.getValue() as string[] | null
        if (!tags || tags.length === 0) return <span className="text-gray-500">—</span>
        return (
          <div className="flex items-center gap-2">
            {tags.slice(0,3).map(t => <span key={t} className="text-[10px] px-2 py-0.5 rounded bg-surface-card border border-surface-border text-gray-300">{t}</span>)}
            {tags.length > 3 && <span className="text-[10px] text-gray-500">+{tags.length - 3}</span>}
          </div>
        )
      }
    }),
    columnHelper.accessor('added_at', {
      header: 'ACQUIRED_AT',
      cell: info => {
        const val = info.getValue()
        return val ? (
          <div className="flex flex-col">
            <span className="text-gray-300">{formatET(val)}</span>
            <span className="text-[10px] text-gray-500">{relativeTime(val)}</span>
          </div>
        ) : <span className="text-gray-500">—</span>
      },
    }),
    columnHelper.accessor('managed_since', {
      header: 'MANAGED_SINCE',
      cell: info => {
        const val = info.getValue()
        return val ? (
          <div className="flex flex-col">
            <span className="text-brand font-medium drop-shadow-[0_0_5px_rgba(99,102,241,0.5)]">{formatET(val)}</span>
            <span className="text-[10px] text-gray-500">{relativeTime(val)}</span>
          </div>
        ) : <span className="text-gray-500">—</span>
      },
    }),
  ], [])

  // Apply client-side tag filtering and confidence sorting before passing to the table
  const filteredData = useMemo(() => {
    let rows = data
    if (tagFilter) {
      const q = tagFilter.trim().toLowerCase()
      rows = rows.filter(r => Array.isArray(r.tags) && r.tags.map((t: string) => t.toLowerCase()).includes(q))
    }
    if (confidenceSort !== 'none') {
      rows = [...rows].sort((a, b) => {
        const av = a.confidence ?? -Infinity
        const bv = b.confidence ?? -Infinity
        return confidenceSort === 'asc' ? av - bv : bv - av
      })
    }
    return rows
  }, [data, tagFilter, confidenceSort])

  const table = useReactTable({
    data: filteredData,
    columns,
    state: { sorting, globalFilter },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  })

  const active = data.filter(s => s.state === 'ACTIVE')
  const managed = data.filter(s => s.state === 'MANAGED')

  return (
    <div className="space-y-6 max-w-[1600px] mx-auto pb-10 h-full flex flex-col">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 border-b border-surface-border pb-4 shrink-0">
        <div>
          <h1 className="text-3xl font-bold text-white tracking-tight flex items-center gap-3">
            <Crosshair className="text-brand" /> 
            Radar Array
          </h1>
          <div className="flex items-center gap-3 mt-2 mono text-xs text-gray-500">
            <span>ACTIVE_TARGETS: <span className="text-white">{active.length}</span></span>
            <span>|</span>
            <span>MANAGED_TARGETS: <span className="text-brand">{managed.length}</span></span>
          </div>
        </div>
        
        <div className="flex items-center gap-3">
          {/* Omni-Filter */}
          <div className="relative group hidden md:block">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 group-focus-within:text-brand transition-colors" />
            <input
              type="text"
              value={globalFilter ?? ''}
              onChange={e => setGlobalFilter(e.target.value)}
              placeholder="Scan array..."
              className="bg-[#12141f] border border-surface-border rounded-lg py-1.5 pl-9 pr-4 text-white font-mono text-sm focus:outline-none focus:border-brand/50 focus:ring-1 focus:ring-brand/50 w-48 transition-all"
            />
          </div>
          <div className="w-[1px] h-6 bg-surface-border"></div>
          <div className="flex items-center gap-2">
            <input
              placeholder="Filter tag..."
              value={tagFilter}
              onChange={e => setTagFilter(e.target.value)}
              className="bg-[#12141f] border border-surface-border rounded px-2 py-1 text-xs mono text-gray-300 focus:outline-none"
            />
            <div className="flex items-center gap-1">
              <button
                onClick={() => setConfidenceSort(s => s === 'asc' ? 'none' : 'asc')}
                className={clsx('text-[10px] px-2 py-1 rounded', confidenceSort === 'asc' ? 'bg-brand/20 text-brand' : 'text-gray-500')}
              >Conf ↑</button>
              <button
                onClick={() => setConfidenceSort(s => s === 'desc' ? 'none' : 'desc')}
                className={clsx('text-[10px] px-2 py-1 rounded', confidenceSort === 'desc' ? 'bg-brand/20 text-brand' : 'text-gray-500')}
              >Conf ↓</button>
            </div>
          </div>
          <button onClick={() => refetch()} className="btn-ghost flex items-center gap-2 px-3">
            <RefreshCw size={14} className={isLoading || isRefetching ? 'animate-spin text-brand' : ''} />
            <span className="mono text-xs uppercase tracking-wider">Sync Array</span>
          </button>
        </div>
      </div>

      {/* Manual Override Console */}
      <div className="card space-y-4 bg-[#0d0f18] shrink-0 border-brand/20">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex gap-2 bg-[#12141f] p-1 rounded-lg border border-surface-border self-start">
            {['', 'ACTIVE', 'MANAGED'].map(s => (
              <button
                key={s}
                onClick={() => setFilterState(s)}
                className={clsx(
                  "px-4 py-1.5 rounded-md text-[10px] font-mono uppercase tracking-widest transition-all",
                  filterState === s 
                    ? "bg-brand/20 text-brand font-bold border border-brand/30 shadow-[0_0_10px_rgba(99,102,241,0.2)]" 
                    : "text-gray-500 hover:text-gray-300 border border-transparent"
                )}
              >
                {s || 'ALL_STATES'}
              </button>
            ))}
            <div className="w-px bg-surface-border mx-1" />
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

          <button
            onClick={() => setJsonOpen(o => !o)}
            className="flex items-center gap-2 text-xs font-mono font-bold tracking-widest uppercase text-brand hover:text-white transition-colors px-3 py-1.5 rounded border border-brand/30 hover:bg-brand/10"
          >
            <TerminalSquare size={14} />
            {jsonOpen ? 'Close Terminal' : 'Inject Payload'}
          </button>
        </div>

        {jsonOpen && (
          <div className="pt-4 border-t border-surface-border space-y-3 animate-in fade-in slide-in-from-top-2 duration-200">
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-gray-500 mono uppercase tracking-widest flex items-center gap-2">
                <TerminalSquare size={12} /> Awaiting raw JSON sequence...
              </span>
              {updateResult && (
                <button onClick={() => setUpdateResult(null)} className="text-[10px] text-gray-500 hover:text-white mono uppercase">
                  [ CLEAR_BUFFER ]
                </button>
              )}
            </div>
            
            <textarea
              className="w-full bg-[#0b0c13] border border-surface-border rounded p-4 text-xs mono text-gray-300 focus:outline-none focus:border-brand focus:ring-1 focus:ring-brand resize-none shadow-card-inset"
              rows={8}
              value={jsonInput}
              onChange={e => setJsonInput(e.target.value)}
              spellCheck="false"
            />
            
            <div className="flex items-center gap-4">
              <button onClick={handleSubmit} className="btn-primary flex items-center gap-2 py-2 px-6" disabled={mutation.isPending}>
                {mutation.isPending ? <RefreshCw size={14} className="animate-spin" /> : <Activity size={14} />}
                <span className="mono text-xs uppercase tracking-widest font-bold">Execute Injection</span>
              </button>
            </div>

            {updateResult && (
              <pre className={clsx(
                "rounded border p-3 text-[10px] mono overflow-auto max-h-48 mt-2",
                updateResult.includes('[SYS_ERROR]') ? "bg-system-offline/10 border-system-offline/30 text-system-offline" : "bg-system-online/10 border-system-online/30 text-system-online"
              )}>
                {updateResult}
              </pre>
            )}
          </div>
        )}
      </div>

      {/* Target Data Grid */}
      <div className="card p-0 flex-1 flex flex-col overflow-hidden border border-surface-border bg-surface-card/40 backdrop-blur-sm relative shadow-card-inset">
        {isLoading ? (
          <div className="flex-1 flex flex-col items-center justify-center text-gray-500 gap-3 min-h-[400px]">
             <Activity className="animate-pulse-slow text-brand" size={32} />
             <span className="mono text-xs uppercase tracking-widest">Scanning Radar Frequencies...</span>
          </div>
        ) : data.length === 0 ? (
          <div className="flex-1 flex items-center justify-center text-gray-500 mono text-sm uppercase tracking-widest min-h-[400px]">
            No Targets Identified On Radar
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
                {table.getRowModel().rows.map(row => {
                  const addedAt = row.original.added_at
                  let isStale = false
                  if (addedAt) {
                    try {
                      const then = new Date(addedAt).getTime()
                      const ageMs = Date.now() - then
                      // Mark stale if older than 7 days
                      isStale = ageMs > 7 * 24 * 60 * 60 * 1000
                    } catch (err) {
                      console.debug('Watchlist: failed to parse added_at', err)
                    }
                  }
                  return (
                    <tr key={row.id} className={clsx("border-b border-surface-border/30 hover:bg-white/[0.02] transition-colors group", isStale && "bg-yellow-900/5") }>
                      {row.getVisibleCells().map(cell => (
                        <td key={cell.id} className="py-2.5 px-5 whitespace-nowrap">
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </td>
                      ))}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
        {/* Table Footer */}
        <div className="bg-[#0b0c13] border-t border-surface-border px-5 py-2 flex justify-between items-center text-[10px] mono text-gray-600 uppercase tracking-widest shrink-0">
          <span>{table.getRowModel().rows.length} Targets Tracking</span>
          <span>Matrix Status: <span className="text-system-online">Active</span></span>
        </div>
      </div>
    </div>
  )
}