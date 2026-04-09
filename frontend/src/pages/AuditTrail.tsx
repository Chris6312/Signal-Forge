import React, { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  SortingState,
} from '@tanstack/react-table'
import { fetchAuditEvents, fetchEventTypes } from '@/api/endpoints'
import { RefreshCw, Filter, FileText, ChevronRight, ChevronDown, TerminalSquare, ArrowUpDown } from 'lucide-react'
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
  SYSTEM: 'bg-gray-500/10 text-gray-400 border-gray-500/30',
  DISCORD: 'bg-[#5865F2]/10 text-[#5865F2] border-[#5865F2]/30 shadow-[0_0_10px_rgba(88,101,242,0.2)]',
  USER: 'bg-brand/10 text-brand border-brand/30 shadow-[0_0_10px_rgba(99,102,241,0.2)]',
  BROKER: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
  WORKER: 'bg-purple-500/10 text-purple-400 border-purple-500/30',
}

const eventTypeColors: Record<string, string> = {
  POSITION_OPENED: 'text-system-online drop-shadow-[0_0_5px_rgba(16,185,129,0.5)]',
  POSITION_CLOSED: 'text-gray-400',
  STOP_UPDATED: 'text-amber-400 drop-shadow-[0_0_5px_rgba(245,158,11,0.5)]',
  PARTIAL_EXIT: 'text-sky-400',
  WATCHLIST_UPDATED: 'text-brand',
  WATCHLIST_SYMBOL_MANAGED: 'text-amber-400',
  WATCHLIST_SYMBOL_REMOVED: 'text-system-offline',
}

const columnHelper = createColumnHelper<AuditEvent>()

export default function AuditTrail() {
  const [filterType, setFilterType] = useState('')
  const [filterSymbol, setFilterSymbol] = useState('')
  const [filterSource, setFilterSource] = useState('')
  const [filterClass, setFilterClass] = useState('')
  const [expanded, setExpanded] = useState<string | null>(null)
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [sorting, setSorting] = useState<SortingState>([{ id: 'created_at', desc: true }])

  const params: Record<string, string> = { limit: '200' }
  if (filterType) params.event_type = filterType
  if (filterSymbol) params.symbol = filterSymbol.toUpperCase()
  if (filterSource) params.source = filterSource
  if (filterClass) params.asset_class = filterClass

  const { data: events = [], isLoading, isRefetching, refetch } = useQuery<AuditEvent[]>({
    queryKey: ['audit', filterType, filterSymbol, filterSource, filterClass],
    queryFn: () => fetchAuditEvents(params),
    refetchInterval: 15000,
  })

  const { data: typesData } = useQuery<{ event_types: string[] }>({
    queryKey: ['audit-event-types'],
    queryFn: fetchEventTypes,
  })

  const columns = useMemo(() => [
    columnHelper.accessor('created_at', {
      header: 'TIMESTAMP',
      cell: info => {
        const val = info.getValue()
        return val ? (
          <div className="flex flex-col">
            <span className="text-gray-300">{formatET(val)}</span>
            <span className="text-[10px] text-gray-500">{relativeTime(val)}</span>
          </div>
        ) : <span className="text-gray-500">—</span>
      }
    }),
    columnHelper.accessor('event_type', {
      header: 'SYS_EVENT',
      cell: info => <span className={clsx('font-bold tracking-wider', eventTypeColors[info.getValue()] || 'text-gray-300')}>{info.getValue()}</span>
    }),
    columnHelper.accessor('symbol', {
      header: 'VECTOR_LINK',
      cell: info => {
        const sym = info.getValue()
        const cls = info.row.original.asset_class
        if (!sym) return <span className="text-gray-600">—</span>
        return (
          <div className="flex items-center gap-2">
             <span className="text-white font-bold tracking-wider">{sym}</span>
             {cls && <span className={clsx(
               "text-[9px] px-1.5 py-0.5 rounded border",
               cls === 'crypto' ? 'bg-violet-500/10 text-violet-400 border-violet-500/30' : 'bg-sky-500/10 text-sky-400 border-sky-500/30'
             )}>{cls.toUpperCase()}</span>}
          </div>
        )
      }
    }),
    columnHelper.accessor('source', {
      header: 'ORIGIN_NODE',
      cell: info => <span className={clsx('badge', sourceColors[info.getValue()] || 'bg-gray-500/20 text-gray-400 border-gray-500/30')}>{info.getValue()}</span>
    }),
    columnHelper.accessor('message', {
      header: 'LOG_OUTPUT',
      cell: info => <span className="text-gray-400 max-w-[300px] truncate inline-block" title={info.getValue() || ''}>{info.getValue() || '—'}</span>
    }),
    columnHelper.display({
      id: 'expand',
      header: 'PAYLOAD',
      cell: info => {
        const hasData = info.row.original.event_data && Object.keys(info.row.original.event_data).length > 0
        const isExp = expanded === info.row.original.id
        if (!hasData) return <span className="text-gray-600 pl-4">—</span>
        return (
          <button 
            className={clsx(
              "flex items-center gap-1 text-[10px] uppercase tracking-widest font-bold px-2 py-1 rounded transition-colors",
              isExp ? "bg-brand text-white" : "bg-surface-card border border-surface-border text-gray-400 hover:text-white"
            )}
          >
            {isExp ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            JSON
          </button>
        )
      }
    })
  ], [expanded])

  const table = useReactTable({
    data: events,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  return (
    <div className="space-y-6 max-w-[1600px] mx-auto pb-10 h-full flex flex-col">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 border-b border-surface-border pb-4 shrink-0">
        <div>
          <h1 className="text-3xl font-bold text-white tracking-tight flex items-center gap-3">
            <FileText className="text-brand" /> 
            System Audit Trail
          </h1>
          <div className="flex items-center gap-3 mt-2 mono text-xs text-gray-500">
            <span>INDEXED_EVENTS: <span className="text-white">{events.length}</span></span>
            <span>|</span>
            <span className="text-system-online">IMMUTABLE_LOG_ACTIVE</span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={() => setFiltersOpen(o => !o)} className={clsx(
            "flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm mono uppercase tracking-wider transition-colors border",
            filtersOpen ? "bg-brand/20 text-brand border-brand/40 shadow-[0_0_10px_rgba(99,102,241,0.2)]" : "bg-surface-card border-surface-border text-gray-400 hover:text-white hover:border-gray-500"
          )}>
            <Filter size={14} />
            Matrix Filters
          </button>
          <div className="w-[1px] h-6 bg-surface-border"></div>
          <button onClick={() => refetch()} className="btn-ghost flex items-center gap-2 px-3">
            <RefreshCw size={14} className={isLoading || isRefetching ? 'animate-spin text-brand' : ''} />
            <span className="mono text-xs uppercase tracking-wider">Sync Logs</span>
          </button>
        </div>
      </div>

      {/* Filter Console */}
      {filtersOpen && (
        <div className="card bg-[#0d0f18] shrink-0 border-brand/20 shadow-card-inset flex flex-wrap gap-4 items-end animate-in fade-in slide-in-from-top-2 duration-200">
          <div className="flex flex-col gap-1.5 flex-1 min-w-[200px]">
            <label className="text-[10px] text-gray-500 mono uppercase tracking-widest flex items-center gap-1.5"><TerminalSquare size={10} /> Event Signature</label>
            <select
              value={filterType}
              onChange={e => setFilterType(e.target.value)}
              className="bg-[#12141f] border border-surface-border rounded px-3 py-2 text-sm mono text-white focus:outline-none focus:border-brand focus:ring-1 focus:ring-brand transition-all w-full"
            >
              <option value="">ALL_SIGNATURES</option>
              {typesData?.event_types.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          
          <div className="flex flex-col gap-1.5 w-32">
            <label className="text-[10px] text-gray-500 mono uppercase tracking-widest">Vector Link</label>
            <input
              type="text"
              value={filterSymbol}
              onChange={e => setFilterSymbol(e.target.value)}
              placeholder="e.g. AAPL"
              className="bg-[#12141f] border border-surface-border rounded px-3 py-2 text-sm mono text-white focus:outline-none focus:border-brand focus:ring-1 focus:ring-brand transition-all uppercase w-full"
            />
          </div>
          
          <div className="flex flex-col gap-1.5 w-40">
            <label className="text-[10px] text-gray-500 mono uppercase tracking-widest">Origin Node</label>
            <select
              value={filterSource}
              onChange={e => setFilterSource(e.target.value)}
              className="bg-[#12141f] border border-surface-border rounded px-3 py-2 text-sm mono text-white focus:outline-none focus:border-brand focus:ring-1 focus:ring-brand transition-all w-full uppercase"
            >
              <option value="">ALL_NODES</option>
              {['SYSTEM', 'DISCORD', 'USER', 'BROKER', 'WORKER'].map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          
          <div className="flex flex-col gap-1.5 w-40">
            <label className="text-[10px] text-gray-500 mono uppercase tracking-widest">Asset Class</label>
            <select
              value={filterClass}
              onChange={e => setFilterClass(e.target.value)}
              className="bg-[#12141f] border border-surface-border rounded px-3 py-2 text-sm mono text-white focus:outline-none focus:border-brand focus:ring-1 focus:ring-brand transition-all w-full uppercase"
            >
              <option value="">GLOBAL_SCOPE</option>
              <option value="crypto">Node_A: Crypto</option>
              <option value="stock">Node_B: Stock</option>
            </select>
          </div>
          
          <button
            onClick={() => { setFilterType(''); setFilterSymbol(''); setFilterSource(''); setFilterClass('') }}
            className="btn-ghost py-2 text-xs mono uppercase tracking-widest font-bold"
          >
            Reset Array
          </button>
        </div>
      )}

      {/* Log Data Grid */}
      <div className="card p-0 flex-1 flex flex-col overflow-hidden border border-surface-border bg-surface-card/40 backdrop-blur-sm relative shadow-card-inset">
        {isLoading ? (
          <div className="flex-1 flex flex-col items-center justify-center text-gray-500 gap-3 min-h-[400px]">
             <RefreshCw className="animate-spin text-brand" size={32} />
             <span className="mono text-xs uppercase tracking-widest">Extracting Log Blocks...</span>
          </div>
        ) : events.length === 0 ? (
          <div className="flex-1 flex items-center justify-center text-gray-500 mono text-sm uppercase tracking-widest min-h-[400px]">
            No System Events Found Matching Filter Criteria
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
                  const isExp = expanded === row.original.id
                  return (
                    <React.Fragment key={row.id}>
                      <tr 
                        className={clsx(
                          "border-b border-surface-border/30 hover:bg-white/[0.02] transition-colors cursor-pointer group",
                          isExp ? "bg-brand/5 border-l-2 border-l-brand" : "border-l-2 border-transparent"
                        )}
                        onClick={() => setExpanded(isExp ? null : row.original.id)}
                      >
                        {row.getVisibleCells().map(cell => (
                          <td key={cell.id} className="py-2.5 px-5 whitespace-nowrap">
                            {flexRender(cell.column.columnDef.cell, cell.getContext())}
                          </td>
                        ))}
                      </tr>
                      {/* JSON Payload Expansion Row */}
                      {isExp && row.original.event_data && (
                        <tr className="border-b border-surface-border bg-[#0b0c13] shadow-card-inset animate-in fade-in duration-200">
                          <td colSpan={6} className="px-5 py-4">
                            <div className="bg-[#12141f] border border-surface-border rounded-lg p-4 relative overflow-hidden">
                              <div className="absolute top-0 left-0 w-full h-[1px] bg-gradient-to-r from-brand/50 to-transparent"></div>
                              <div className="text-[10px] text-brand mono uppercase tracking-widest mb-2 flex items-center gap-2">
                                <TerminalSquare size={12} /> Raw JSON Sequence
                              </div>
                              <pre className="text-xs mono text-gray-300 overflow-auto max-h-60 scrollbar-thin">
                                {JSON.stringify(row.original.event_data, null, 2)}
                              </pre>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
        <div className="bg-[#0b0c13] border-t border-surface-border px-5 py-2 flex justify-between items-center text-[10px] mono text-gray-600 uppercase tracking-widest shrink-0">
          <span>{table.getRowModel().rows.length} Events Rendered</span>
          <span>Buffer: <span className="text-system-online">Synced</span></span>
        </div>
      </div>
    </div>
  )
}