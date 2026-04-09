import { useState, useMemo } from 'react'
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
import { fetchPositions } from '@/api/endpoints'
import { Search, ArrowUpDown, TrendingUp, Activity, RefreshCw } from 'lucide-react'
import StatusBadge from '@/components/StatusBadge'
import clsx from 'clsx'

interface Position {
  id: string
  symbol: string
  asset_class: 'crypto' | 'stock'
  side: 'long' | 'short' | 'buy' | 'sell'
  quantity: number
  entry_price: number
  current_price: number
  unrealized_pnl: number
  status: string
  updated_at: string
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
  const [sorting, setSorting] = useState<SortingState>([{ id: 'unrealized_pnl', desc: true }])
  const [globalFilter, setGlobalFilter] = useState('')

  // We use useQuery and ensure we default to an empty array even if the API returns a non-array response
  const { data, isLoading, isRefetching, refetch } = useQuery<Position[]>({
    queryKey: ['positions'],
    queryFn: () => fetchPositions(),
    // Defaulting staleTime to 10s to keep it fresh without overloading
    staleTime: 10000, 
  })

  // Ensure positions is always an array to prevent .reduce/filter crashes
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
    columnHelper.accessor('side', {
      header: 'DIR',
      cell: info => {
        const val = info.getValue()
        if (!val) return <span className="text-gray-500">—</span>
        const side = val.toUpperCase()
        const isLong = side === 'LONG' || side === 'BUY'
        return (
          <span className={clsx(
            "text-[10px] px-1.5 py-0.5 rounded border tracking-widest font-bold",
            isLong ? "border-system-online/30 text-system-online bg-system-online/10" : "border-system-offline/30 text-system-offline bg-system-offline/10"
          )}>
            {side}
          </span>
        )
      }
    }),
    columnHelper.accessor('quantity', {
      header: 'SIZE',
      cell: info => <span className="text-gray-300">{(info.getValue() ?? 0).toString()}</span>,
    }),
    columnHelper.accessor('entry_price', {
      header: 'ENTRY_Px',
      cell: info => <span className="text-gray-400">{formatCurrency(info.getValue())}</span>,
    }),
    columnHelper.accessor('current_price', {
      header: 'MARK_Px',
      cell: info => <span className="text-white font-medium">{formatCurrency(info.getValue())}</span>,
    }),
    columnHelper.accessor('unrealized_pnl', {
      header: 'LIVE_DELTA (PnL)',
      cell: info => {
        const val = info.getValue() ?? 0
        return (
          <span className={clsx(
            "font-bold transition-colors duration-300",
            val > 0 ? "text-system-online drop-shadow-[0_0_8px_rgba(16,185,129,0.3)]" : 
            val < 0 ? "text-system-offline drop-shadow-[0_0_8px_rgba(239,68,68,0.3)]" : "text-gray-400"
          )}>
            {val > 0 ? '▲' : val < 0 ? '▼' : '▬'} {formatPnL(val)}
          </span>
        )
      },
    }),
    columnHelper.accessor('status', {
      header: 'STATE',
      cell: info => <StatusBadge status={info.getValue() || 'unknown'} />,
    }),
  ], [])

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

  // Safe aggregate calculations
  const totalPnL = positions.reduce((acc, pos) => acc + (pos.unrealized_pnl || 0), 0)
  const openCount = positions.filter(p => p.status === 'open' || p.status === 'OPEN').length

  return (
    <div className="space-y-6 max-w-[1600px] mx-auto pb-10 h-full flex flex-col">
      {/* Page Header */}
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
              placeholder="Filter by Symbol..."
              className="bg-[#12141f] border border-surface-border rounded-lg py-1.5 pl-9 pr-4 text-white font-mono text-sm focus:outline-none focus:border-brand/50 focus:ring-1 focus:ring-brand/50 w-64 transition-all"
            />
          </div>
          
          <button onClick={() => refetch()} className="btn-ghost flex items-center gap-2 px-3" disabled={isRefetching}>
            <RefreshCw size={14} className={isRefetching ? "animate-spin text-brand" : ""} />
            <span className="sr-only">Refresh</span>
          </button>
        </div>
      </div>

      {/* Main Data Grid */}
      <div className="card p-0 flex-1 flex flex-col overflow-hidden border border-surface-border bg-surface-card/40 backdrop-blur-sm relative z-10 shadow-card-inset">
        {isLoading ? (
          <div className="flex-1 flex flex-col items-center justify-center text-gray-500 gap-3 min-h-[400px]">
             <Activity className="animate-pulse-slow text-brand" size={32} />
             <span className="mono text-xs uppercase tracking-widest">Compiling Matrix Data...</span>
          </div>
        ) : positions.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center text-gray-500 min-h-[400px]">
            <span className="mono text-sm uppercase tracking-widest">No Active Vectors Found</span>
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
                          "py-4 px-5 text-xs font-mono font-bold uppercase tracking-widest text-gray-500 bg-surface-card/80 backdrop-blur-md select-none whitespace-nowrap",
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
                  <tr key={row.id} className="border-b border-surface-border/50 hover:bg-white/[0.02] transition-colors group">
                    {row.getVisibleCells().map(cell => (
                      <td key={cell.id} className="py-3.5 px-5 whitespace-nowrap">
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="bg-[#0b0c13] border-t border-surface-border px-5 py-2.5 flex justify-between items-center text-[10px] mono text-gray-600 uppercase tracking-widest shrink-0">
          <span>{table.getRowModel().rows.length} Vectors Rendered</span>
          <span>Matrix Status: <span className="text-system-online">Nominal</span></span>
        </div>
      </div>
    </div>
  )
}