import React, { useState, useMemo } from 'react'
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
import { fetchOpenPositions } from '@/api/endpoints'
import { 
  Search, ArrowUpDown, TrendingUp, Activity, RefreshCw, 
  ChevronRight, ChevronDown, Target, Shield, Zap, Info, Wallet
} from 'lucide-react'
import StatusBadge from '@/components/StatusBadge'
import { formatET, relativeTime } from '@/utils/time'
import clsx from 'clsx'

interface Position {
  id: string
  symbol: string
  asset_class: 'crypto' | 'stock'
  state: string
  quantity: number
  entry_price: number
  current_price: number
  pnl_unrealized: number
  entry_time: string | null
  // Expansion Data
  profit_target_1: number | null
  profit_target_2: number | null
  initial_stop: number | null
  current_stop: number | null
  entry_strategy: string | null
  exit_strategy: string | null
  pnl_realized: number | null
  fees_paid: number | null
  regime_at_entry: string | null
}

const columnHelper = createColumnHelper<Position>()

function formatCurrency(val: number | null | undefined) {
  if (val == null) return '$0.00'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 4 }).format(val)
}

function formatPnL(val: number | null | undefined) {
  if (val == null) return '0.00'
  const formatted = new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Math.abs(val))
  return val >= 0 ? `+${formatted}` : `-${formatted}`
}

export default function Positions() {
  const [sorting, setSorting] = useState<SortingState>([{ id: 'pnl_unrealized', desc: true }])
  const [globalFilter, setGlobalFilter] = useState('')
  const [expanded, setExpanded] = useState<string | null>(null)

  const { data, isLoading, isRefetching, refetch } = useQuery<Position[]>({
    queryKey: ['positions', 'open'],
    queryFn: () => fetchOpenPositions(),
    staleTime: 10000, 
  })

  const positions = useMemo(() => Array.isArray(data) ? data : [], [data])

  const columns = useMemo(() => [
    columnHelper.accessor('symbol', {
      header: 'VECTOR (SYM)',
      cell: info => (
        <div className="flex items-center gap-2">
          <div className={clsx(
            "w-1.5 h-1.5 rounded-full shadow-[0_0_5px_currentColor]",
            info.row.original.asset_class === 'crypto' ? 'text-[#5865F2] bg-[#5865F2]' : 'text-system-online bg-system-online'
          )}></div>
          <span className="font-bold tracking-wider text-white">{info.getValue() || 'UNKNOWN'}</span>
        </div>
      ),
    }),
    columnHelper.accessor('state', {
      header: 'STATUS',
      cell: info => <StatusBadge status={info.getValue() || 'unknown'} />,
    }),
    columnHelper.accessor('entry_time', {
      header: 'ACQUIRED_AT',
      cell: info => {
        const val = info.getValue()
        return val ? (
          <div className="flex flex-col">
            <span className="text-gray-300 text-xs">{formatET(val)}</span>
            <span className="text-[10px] text-gray-500 font-mono">{relativeTime(val)}</span>
          </div>
        ) : <span className="text-gray-500">—</span>
      },
    }),
    columnHelper.accessor('entry_price', {
      header: 'ENTRY_Px',
      cell: info => <span className="text-gray-400 font-mono">{formatCurrency(info.getValue())}</span>,
    }),
    columnHelper.accessor('current_price', {
      header: 'MARK_Px',
      cell: info => <span className="text-white font-medium font-mono">{formatCurrency(info.getValue())}</span>,
    }),
    columnHelper.accessor('pnl_unrealized', {
      header: 'LIVE_DELTA',
      cell: info => {
        const val = info.getValue() ?? 0
        return (
          <span className={clsx(
            "font-bold font-mono transition-colors duration-300",
            val > 0 ? "text-system-online drop-shadow-[0_0_8px_rgba(16,185,129,0.3)]" : 
            val < 0 ? "text-system-offline drop-shadow-[0_0_8px_rgba(239,68,68,0.3)]" : "text-gray-400"
          )}>
            {val > 0 ? '▲' : val < 0 ? '▼' : '▬'} {formatPnL(val)}
          </span>
        )
      },
    }),
    columnHelper.display({
      id: 'actions',
      header: 'MGMT',
      cell: info => {
        const isExp = expanded === info.row.original.id
        return (
          <div className="flex justify-center">
            {isExp ? <ChevronDown size={16} className="text-brand" /> : <ChevronRight size={16} className="text-gray-600 group-hover:text-brand transition-colors" />}
          </div>
        )
      }
    }),
  ], [expanded])

  const table = useReactTable({
    data: positions,
    columns,
    state: { sorting, globalFilter },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  })

  const totalPnL = positions.reduce((acc, pos) => acc + (pos.pnl_unrealized || 0), 0)
  const openCount = positions.filter(p => p.state === 'OPEN').length

  return (
    <div className="space-y-6 max-w-[1600px] mx-auto pb-10 h-full flex flex-col">
      {/* Header logic remains identical to previous turn */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 border-b border-surface-border pb-4 shrink-0">
        <div>
          <h1 className="text-3xl font-bold text-white tracking-tight flex items-center gap-3">
            <TrendingUp className="text-brand" /> 
            Active Vectors
          </h1>
          <div className="flex items-center gap-3 mt-2 mono text-xs text-gray-500">
            <span>TOTAL_EXPOSURE: <span className="text-white">{positions.length}</span></span>
            <span>|</span>
            <span>OPEN_OPS: <span className="text-white">{openCount}</span></span>
            <span>|</span>
            <span>AGG_DELTA: 
              <span className={clsx("ml-1 font-bold", totalPnL >= 0 ? "text-system-online" : "text-system-offline")}>
                {formatPnL(totalPnL)}
              </span>
            </span>
          </div>
        </div>
        
        <div className="flex items-center gap-3">
          <div className="relative group">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 group-focus-within:text-brand transition-colors" />
            <input
              type="text"
              value={globalFilter ?? ''}
              onChange={e => setGlobalFilter(e.target.value)}
              placeholder="Scan Vectors..."
              className="bg-[#12141f] border border-surface-border rounded-lg py-1.5 pl-9 pr-4 text-white font-mono text-sm focus:outline-none focus:border-brand/50 focus:ring-1 focus:ring-brand/50 w-64 transition-all"
            />
          </div>
          <button onClick={() => refetch()} className="btn-ghost flex items-center gap-2 px-3">
            <RefreshCw size={14} className={isRefetching ? "animate-spin text-brand" : ""} />
          </button>
        </div>
      </div>

      <div className="card p-0 flex-1 flex flex-col overflow-hidden border border-surface-border bg-surface-card/40 backdrop-blur-sm relative z-10 shadow-card-inset">
        <div className="overflow-auto flex-1 scrollbar-thin">
          <table className="w-full text-left border-collapse">
            <thead className="sticky top-0 z-20 bg-[#0b0c13] border-b border-surface-border">
              {table.getHeaderGroups().map(headerGroup => (
                <tr key={headerGroup.id}>
                  {headerGroup.headers.map(header => (
                    <th key={header.id} className="py-4 px-5 text-[10px] font-mono font-bold uppercase tracking-widest text-gray-500">
                      {flexRender(header.column.columnDef.header, header.getContext())}
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody>
              {table.getRowModel().rows.map(row => {
                const isExp = expanded === row.original.id
                return (
                  <React.Fragment key={row.id}>
                    <tr 
                      className={clsx(
                        "border-b border-surface-border/30 hover:bg-white/[0.02] transition-colors cursor-pointer group",
                        isExp ? "bg-brand/5" : ""
                      )}
                      onClick={() => setExpanded(isExp ? null : row.original.id)}
                    >
                      {row.getVisibleCells().map(cell => (
                        <td key={cell.id} className="py-3 px-5 whitespace-nowrap">
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </td>
                      ))}
                    </tr>
                    {isExp && (
                      <tr className="bg-[#0b0c13]/80 animate-in fade-in duration-200">
                        <td colSpan={7} className="px-8 py-6 border-b border-surface-border/50">
                          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8">
                            {/* Column 1: Core Trade Parameters */}
                            <div className="space-y-4">
                              <SubMetric label="QUANTITY" value={row.original.quantity} mono icon={<Activity size={10} />} />
                              <SubMetric label="REGIME_AT_ENTRY" value={row.original.regime_at_entry} icon={<Zap size={10} />} />
                            </div>

                            {/* Column 2: Protection & Targets */}
                            <div className="space-y-4">
                              <SubMetric label="STOP_LOSS" value={formatCurrency(row.original.current_stop || row.original.initial_stop)} color="text-system-offline" icon={<Shield size={10} />} />
                              <SubMetric label="INITIAL_STOP" value={formatCurrency(row.original.initial_stop)} color="text-gray-500" />
                            </div>

                            {/* Column 3: Profit Objectives */}
                            <div className="space-y-4">
                              <SubMetric label="TARGET_1 (TP1)" value={formatCurrency(row.original.profit_target_1)} color="text-system-online" icon={<Target size={10} />} />
                              <SubMetric label="TARGET_2 (TP2)" value={formatCurrency(row.original.profit_target_2)} color="text-system-online" />
                            </div>

                            {/* Column 4: Strategy & Performance */}
                            <div className="space-y-4">
                              <SubMetric label="ALGO_ENTRY" value={row.original.entry_strategy} icon={<Info size={10} />} />
                              <SubMetric label="REALIZED_PnL" value={formatPnL(row.original.pnl_realized)} color={row.original.pnl_realized && row.original.pnl_realized >= 0 ? "text-system-online" : "text-system-offline"} icon={<Wallet size={10} />} />
                            </div>
                          </div>

                          {/* Secondary Row for Metadata */}
                          <div className="mt-6 pt-4 border-t border-surface-border/30 flex gap-10 text-[10px] mono text-gray-500 uppercase tracking-widest">
                             <div>ALGO_EXIT: <span className="text-gray-300 ml-1">{row.original.exit_strategy || 'ACTIVE_MONITORING'}</span></div>
                             <div>FEES_PAID: <span className="text-system-offline ml-1">{formatCurrency(row.original.fees_paid)}</span></div>
                             <div>SOURCE_ID: <span className="text-brand ml-1">{row.original.watchlist_source_id || 'MANUAL'}</span></div>
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
      </div>
    </div>
  )
}

function SubMetric({ label, value, color = "text-gray-300", mono = false, icon }: { label: string, value: any, color?: string, mono?: boolean, icon?: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <div className="text-[9px] text-gray-500 font-mono uppercase tracking-tighter flex items-center gap-1.5">
        {icon}
        {label}
      </div>
      <div className={clsx("text-sm font-bold", color, mono && "font-mono")}>
        {value || '—'}
      </div>
    </div>
  )
}