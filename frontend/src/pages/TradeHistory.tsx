import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table'
import { fetchTradeHistory, fetchTradeSummary } from '@/api/endpoints'
import { Trade, TradeSummary } from '@/api/types'
import MetricCard from '@/components/MetricCard'
import { RefreshCw, Download, Clock, ArrowUpDown, Activity } from 'lucide-react'
import { formatET, relativeTime } from '@/utils/time'
import clsx from 'clsx'

// Use shared types
type LocalSummary = TradeSummary

const columnHelper = createColumnHelper()

type LocalSortingState = Array<{ id: string; desc?: boolean }>

function formatPnL(val: number | null) {
  if (val === null) return '—'
  const formatted = new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 }).format(Math.abs(val))
  return val >= 0 ? `+${formatted}` : `-${formatted}`
}

export default function TradeHistory() {
  const [filterClass, setFilterClass] = useState<string>('')
  const [sorting, setSorting] = useState<LocalSortingState>([{ id: 'exit_time', desc: true }])

  const params: Record<string, string> = {}
  if (filterClass) params.asset_class = filterClass

  const qTrades = useQuery({
    queryKey: ['trades', filterClass],
    queryFn: () => fetchTradeHistory(params),
    refetchInterval: 30000,
  }) as { data?: Trade[]; isLoading?: boolean; refetch?: () => Promise<any>; isRefetching?: boolean }
  const trades = qTrades.data ?? []

  const qSummary = useQuery({
    queryKey: ['trade-summary', filterClass],
    queryFn: () => fetchTradeSummary(filterClass ? { asset_class: filterClass } : {}),
    refetchInterval: 30000,
  }) as { data?: LocalSummary }
  const summary = qSummary.data

  const exportCSV = () => {
    const rows = [
      ['Symbol', 'Class', 'Entry Price', 'Exit Price', 'Qty', 'Entry Time', 'Exit Time', 'PnL Realized', 'Fees Paid', 'Exit Strategy', 'Entry Strategy', 'Regime At Entry'],
      ...trades.map(t => [
        t.symbol,
        t.asset_class,
        t.entry_price ?? '',
        t.exit_price ?? '',
        t.quantity ?? '',
        t.entry_time ? new Date(t.entry_time).toISOString() : '',
        t.exit_time ? new Date(t.exit_time).toISOString() : '',
        t.pnl_realized ?? '',
        t.fees_paid ?? '',
        t.exit_strategy ?? '',
        t.entry_strategy ?? '',
        t.regime_at_entry ?? '',
      ]),
    ]
    const csv = rows.map(r => r.join(',')).join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `forge_executions_${filterClass || 'all'}_${new Date().getTime()}.csv`
    a.click()
  }

  const columns = useMemo(() => [
    columnHelper.accessor('symbol', {
      header: 'VECTOR',
      cell: info => (
        <div className="flex items-center gap-2">
          <div className={clsx(
            "w-1.5 h-1.5 rounded-full shadow-[0_0_5px_currentColor]",
            info.row.original.asset_class === 'crypto' ? 'text-[#5865F2] bg-[#5865F2]' : 'text-system-online bg-system-online'
          )}></div>
          <span className="font-bold tracking-wider text-white">{info.getValue()}</span>
        </div>
      )
    }),
    columnHelper.accessor('entry_price', {
      header: 'ENTRY_Px',
      cell: info => <span className="text-gray-400 font-mono">{info.getValue() == null ? '—' : info.getValue().toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 8 })}</span>
    }),
    columnHelper.accessor('exit_price', {
      header: 'EXIT_Px',
      cell: info => <span className="text-gray-300 font-mono">{info.getValue() == null ? '—' : info.getValue().toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 8 })}</span>
    }),
    columnHelper.accessor('pnl_realized', {
      header: 'REALIZED_DELTA',
      cell: info => {
        const val = info.getValue()
        return (
          <span className={clsx(
            "font-mono font-bold tracking-tight",
            val !== null && val > 0 ? "text-system-online drop-shadow-[0_0_8px_rgba(16,185,129,0.3)]" : 
            val !== null && val < 0 ? "text-system-offline drop-shadow-[0_0_8px_rgba(239,68,68,0.3)]" : "text-gray-500"
          )}>
            {formatPnL(val)}
          </span>
        )
      }
    }),
    columnHelper.accessor('exit_reason', {
      header: 'TRIGGER',
      cell: info => <span className="text-xs text-gray-400 truncate max-w-[150px] inline-block uppercase tracking-wider">{info.getValue() || '—'}</span>
    }),
    columnHelper.accessor('entry_strategy', {
      header: 'ALGO_STRATEGY',
      cell: info => <span className="text-[10px] bg-surface-card border border-surface-border px-1.5 py-0.5 rounded text-gray-400 font-mono">{info.getValue() || '—'}</span>
    }),
    columnHelper.accessor('exit_time', {
      header: 'EXEC_TIME',
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
  ], [])

  const table = useReactTable({
    data: trades,
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
            <Clock className="text-brand" /> 
            Execution Log
          </h1>
          <div className="flex items-center gap-3 mt-2 mono text-xs text-gray-500">
            <span>CLOSED_VECTORS: <span className="text-white">{trades.length}</span></span>
            <span>|</span>
            <span className="text-system-online">DB_CONNECTED</span>
          </div>
        </div>
        <div className="flex items-center gap-3">
  <button onClick={exportCSV} className="btn-ghost flex items-center gap-2 px-3 disabled:opacity-50" disabled={(qTrades.isLoading ?? false) || trades.length === 0}>
            <Download size={14} />
            <span className="mono text-xs uppercase tracking-wider">Dump Telemetry</span>
          </button>
          <div className="w-[1px] h-6 bg-surface-border"></div>
          <button onClick={() => qTrades.refetch?.()} className="btn-ghost flex items-center gap-2 px-3">
            <RefreshCw size={14} className={(qTrades.isLoading ?? false) || (qTrades.isRefetching ?? false) ? 'animate-spin text-brand' : ''} />
            <span className="mono text-xs uppercase tracking-wider">Sync Log</span>
          </button>
        </div>
      </div>

      {/* Summary Metrics Banner */}
      {summary && (
        <div className="card p-4 grid grid-cols-2 md:grid-cols-6 gap-4 bg-gradient-to-r from-surface-card to-brand/5 border-l-2 border-l-brand shrink-0">
          <MetricCard label="Total Executions" value={summary.total_trades} icon={<Activity size={14} />} />
          <MetricCard label="Profitable" value={summary.winners} positive={summary.winners > 0} mono />
          <MetricCard label="Losses" value={summary.losers} negative={summary.losers > 0} mono />
          <MetricCard 
            label="Win Ratio" 
            value={`${summary.win_rate}%`} 
            positive={summary.win_rate >= 50} 
            negative={summary.win_rate < 50} 
            mono 
          />
          <MetricCard
            label="Aggregate Delta"
            value={formatPnL(summary.total_pnl)}
            positive={summary.total_pnl > 0}
            negative={summary.total_pnl < 0}
            mono
          />
          <MetricCard
            label="Mean Delta"
            value={formatPnL(summary.avg_pnl)}
            positive={summary.avg_pnl > 0}
            negative={summary.avg_pnl < 0}
            mono
          />
        </div>
      )}

      {/* Data Grid Section */}
      <div className="flex-1 flex flex-col space-y-3 min-h-[400px]">
        <div className="flex items-center justify-between px-1">
          <div className="text-xs text-brand mono font-bold uppercase tracking-widest">Historical Matrix</div>
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
                {c || 'Global'}
              </button>
            ))}
          </div>
        </div>
        
        <div className="card p-0 flex-1 flex flex-col overflow-hidden border border-surface-border bg-surface-card/40 backdrop-blur-sm relative shadow-card-inset">
          {(qTrades.isLoading ?? false) ? (
            <div className="flex-1 flex flex-col items-center justify-center text-gray-500 gap-3">
               <Activity className="animate-pulse-slow text-brand" size={32} />
               <span className="mono text-xs uppercase tracking-widest">Compiling Trade Archives...</span>
            </div>
          ) : trades.length === 0 ? (
            <div className="flex-1 flex items-center justify-center text-gray-500 mono text-sm uppercase tracking-widest">
              No Execution Logs Found
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
                    <tr key={row.id} className="border-b border-surface-border/30 hover:bg-white/[0.02] transition-colors">
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
          {/* Table Footer */}
          <div className="bg-[#0b0c13] border-t border-surface-border px-5 py-2 flex justify-between items-center text-[10px] mono text-gray-600 uppercase tracking-widest shrink-0">
            <span>{table.getRowModel().rows.length} Vectors Rendered</span>
            <span>Archive Status: <span className="text-system-online">Nominal</span></span>
          </div>
        </div>
      </div>
    </div>
  )
}