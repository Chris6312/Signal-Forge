import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  SortingState,
} from '@tanstack/react-table'
import { fetchLedgerAccounts, fetchLedgerEntries, postAdjustment } from '@/api/endpoints'
import MetricCard from '@/components/MetricCard'
import { RefreshCw, Plus, Download, BookOpen, Activity, ArrowUpDown, TerminalSquare } from 'lucide-react'
import { formatET, relativeTime } from '@/utils/time'
import clsx from 'clsx'

interface LedgerAccount {
  id: string
  asset_class: string
  cash_balance: number
  fees_total: number
  realized_pnl: number
  unrealized_pnl: number
  last_reconciled_at: string | null
  updated_at: string | null
}

interface LedgerEntry {
  id: string
  asset_class: string
  entry_type: string
  symbol: string | null
  amount: number
  balance_after: number
  notes: string | null
  created_at: string | null
}

const columnHelper = createColumnHelper<LedgerEntry>()

function formatCurrency(val: number) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 4 }).format(val)
}

function formatPnL(val: number) {
  const formatted = new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Math.abs(val))
  return val >= 0 ? `+${formatted}` : `-${formatted}`
}

export default function Ledger() {
  const qc = useQueryClient()
  const [filterClass, setFilterClass] = useState<string>('')
  const [adjClass, setAdjClass] = useState<'crypto' | 'stock'>('crypto')
  const [adjAmount, setAdjAmount] = useState('')
  const [adjNotes, setAdjNotes] = useState('')
  const [adjOpen, setAdjOpen] = useState(false)
  const [sorting, setSorting] = useState<SortingState>([{ id: 'created_at', desc: true }])

  const params: Record<string, string> = {}
  if (filterClass) params.asset_class = filterClass

  const { data: accounts = [], isLoading: accsLoading, refetch: refetchAccts } = useQuery<LedgerAccount[]>({
    queryKey: ['ledger-accounts'],
    queryFn: fetchLedgerAccounts,
    refetchInterval: 15000,
  })

  const { data: entries = [], isLoading: entriesLoading, refetch: refetchEntries, isRefetching } = useQuery<LedgerEntry[]>({
    queryKey: ['ledger-entries', filterClass],
    queryFn: () => fetchLedgerEntries(params),
    refetchInterval: 15000,
  })

  const mutation = useMutation({
    mutationFn: (body: { asset_class: string; amount: number; notes: string }) => postAdjustment(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ledger-accounts'] })
      qc.invalidateQueries({ queryKey: ['ledger-entries'] })
      setAdjAmount('')
      setAdjNotes('')
      setAdjOpen(false)
    },
  })

  const handleAdjust = () => {
    const amount = parseFloat(adjAmount)
    if (isNaN(amount)) return
    mutation.mutate({ asset_class: adjClass, amount, notes: adjNotes })
  }

  const exportCSV = () => {
    // Uses the currently loaded/filtered entries
    const rows = [
      ['Timestamp', 'Asset Class', 'Entry Type', 'Symbol', 'Amount', 'Balance After', 'Notes'],
      ...entries.map(e => [
        e.created_at ? new Date(e.created_at).toISOString() : '',
        e.asset_class,
        e.entry_type,
        e.symbol || '',
        e.amount,
        e.balance_after,
        `"${(e.notes || '').replace(/"/g, '""')}"` // Escape quotes for CSV
      ]),
    ]
    const csv = rows.map(r => r.join(',')).join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `forge_ledger_${filterClass || 'all'}_${new Date().getTime()}.csv`
    a.click()
  }

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
    columnHelper.accessor('asset_class', {
      header: 'NODE',
      cell: info => {
        const c = info.getValue()
        return (
          <div className="flex items-center gap-2">
            <div className={clsx(
              "w-1.5 h-1.5 rounded-full shadow-[0_0_5px_currentColor]",
              c === 'crypto' ? 'text-[#5865F2] bg-[#5865F2]' : 'text-system-online bg-system-online'
            )}></div>
            <span className="text-xs font-bold tracking-wider uppercase text-gray-300">{c}</span>
          </div>
        )
      }
    }),
    columnHelper.accessor('entry_type', {
      header: 'OP_TYPE',
      cell: info => <span className="text-gray-400 text-xs tracking-wider uppercase">{info.getValue()}</span>
    }),
    columnHelper.accessor('symbol', {
      header: 'VECTOR',
      cell: info => <span className="text-white font-bold tracking-wider">{info.getValue() || 'SYS_GLOBAL'}</span>
    }),
    columnHelper.accessor('amount', {
      header: 'DELTA_AMT',
      cell: info => {
        const val = info.getValue()
        return (
          <span className={clsx(
            "font-mono font-medium drop-shadow-[0_0_5px_currentColor]",
            val >= 0 ? "text-system-online" : "text-system-offline"
          )}>
            {val >= 0 ? '+' : ''}{val.toFixed(4)}
          </span>
        )
      }
    }),
    columnHelper.accessor('balance_after', {
      header: 'LIQUIDITY_POST',
      cell: info => <span className="text-gray-300 font-mono">{info.getValue().toFixed(4)}</span>
    }),
    columnHelper.accessor('notes', {
      header: 'SYS_LOG',
      cell: info => <span className="text-gray-500 text-xs truncate max-w-[250px] inline-block">{info.getValue() || '—'}</span>
    }),
  ], [])

  const table = useReactTable({
    data: entries,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  const cryptoAcct = accounts.find(a => a.asset_class === 'crypto')
  const stockAcct = accounts.find(a => a.asset_class === 'stock')

  return (
    <div className="space-y-6 max-w-[1600px] mx-auto pb-10 h-full flex flex-col">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 border-b border-surface-border pb-4 shrink-0">
        <div>
          <h1 className="text-3xl font-bold text-white tracking-tight flex items-center gap-3">
            <BookOpen className="text-brand" /> 
            Paper Ledger
          </h1>
          <div className="flex items-center gap-3 mt-2 mono text-xs text-gray-500">
            <span>ISOLATED_FINANCIAL_TRUTH</span>
            <span>|</span>
            <span className="text-system-online animate-pulse">STATE: SYNCED</span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={exportCSV} className="btn-ghost flex items-center gap-2 px-3 disabled:opacity-50" disabled={entriesLoading || entries.length === 0}>
            <Download size={14} />
            <span className="mono text-xs uppercase tracking-wider">Export Matrix</span>
          </button>
          <div className="w-[1px] h-6 bg-surface-border"></div>
          <button onClick={() => { refetchAccts(); refetchEntries() }} className="btn-ghost flex items-center gap-2 px-3">
            <RefreshCw size={14} className={accsLoading || isRefetching ? 'animate-spin text-brand' : ''} />
            <span className="mono text-xs uppercase tracking-wider">Sync State</span>
          </button>
        </div>
      </div>

      {/* Account summaries */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 shrink-0">
        {[
          { label: 'Node_A: Crypto (Kraken)', account: cryptoAcct, color: '#5865F2' },
          { label: 'Node_B: Stocks (Tradier)', account: stockAcct, color: '#10b981' },
        ].map(({ label, account, color }) => (
          <div key={label} className="card space-y-4 relative overflow-hidden group">
            <div className="absolute inset-0 bg-gradient-to-br from-transparent to-surface opacity-0 group-hover:opacity-100 transition-opacity"></div>
            <div className="flex items-center justify-between border-b border-surface-border pb-3 relative z-10">
              <div className="text-xs text-gray-400 mono font-bold uppercase tracking-widest flex items-center gap-2">
                <div className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: color, boxShadow: `0 0 8px ${color}` }}></div>
                {label}
              </div>
            </div>
            
            {accsLoading ? (
              <div className="flex items-center gap-2 text-gray-500 text-sm py-4">
                <Activity size={14} className="animate-pulse" /> Resolving balance...
              </div>
            ) : !account ? (
              <div className="text-gray-500 text-sm py-4 mono">NO_ACTIVE_ACCOUNT_FOUND</div>
            ) : (
              <div className="space-y-4 relative z-10">
                <div className="grid grid-cols-2 gap-3">
                  <MetricCard label="Liquidity (Cash)" value={formatCurrency(account.cash_balance)} mono />
                  <MetricCard label="System Fees" value={account.fees_total.toFixed(4)} mono />
                  <MetricCard
                    label="Realized Delta"
                    value={formatPnL(account.realized_pnl)}
                    positive={account.realized_pnl > 0}
                    negative={account.realized_pnl < 0}
                    mono
                  />
                  <MetricCard
                    label="Unrealized Delta"
                    value={formatPnL(account.unrealized_pnl)}
                    positive={account.unrealized_pnl > 0}
                    negative={account.unrealized_pnl < 0}
                    mono
                  />
                </div>
                {account.last_reconciled_at && (
                  <div className="flex items-center justify-between text-[10px] mono text-gray-600 border-t border-surface-border pt-3">
                    <span>LAST_RECONCILIATION</span>
                    <span className="text-brand">{formatET(account.last_reconciled_at)}</span>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Manual Override Console */}
      <div className="card space-y-4 bg-[#0d0f18] shrink-0 border-brand/20">
        <button
          className="flex items-center justify-between w-full text-sm font-medium text-gray-300 hover:text-white transition-colors group"
          onClick={() => setAdjOpen(o => !o)}
        >
          <div className="flex items-center gap-3">
            <TerminalSquare size={16} className="text-brand group-hover:drop-shadow-[0_0_5px_rgba(99,102,241,0.5)] transition-all" />
            <span className="mono tracking-widest uppercase text-xs">Execute Manual Adjustment</span>
          </div>
          <Plus size={16} className={clsx("transition-transform duration-300 text-gray-500", adjOpen && "rotate-45")} />
        </button>
        
        {adjOpen && (
          <div className="pt-4 border-t border-surface-border flex flex-col md:flex-row gap-4 items-end animate-in fade-in slide-in-from-top-2 duration-200">
            <div className="flex flex-col gap-1.5 w-full md:w-auto">
              <label className="text-[10px] text-gray-500 mono uppercase tracking-widest">Target Node</label>
              <select
                value={adjClass}
                onChange={e => setAdjClass(e.target.value as 'crypto' | 'stock')}
                className="bg-[#12141f] border border-surface-border rounded py-2 px-3 text-white font-mono text-sm focus:outline-none focus:border-brand focus:ring-1 focus:ring-brand transition-all"
              >
                <option value="crypto">Node_A: Crypto</option>
                <option value="stock">Node_B: Stock</option>
              </select>
            </div>
            <div className="flex flex-col gap-1.5 w-full md:w-32">
              <label className="text-[10px] text-gray-500 mono uppercase tracking-widest">Delta Amt</label>
              <input
                type="number"
                placeholder="0.00"
                value={adjAmount}
                onChange={e => setAdjAmount(e.target.value)}
                className="bg-[#12141f] border border-surface-border rounded py-2 px-3 text-white font-mono text-sm focus:outline-none focus:border-brand focus:ring-1 focus:ring-brand transition-all w-full"
              />
            </div>
            <div className="flex flex-col gap-1.5 flex-1 w-full">
              <label className="text-[10px] text-gray-500 mono uppercase tracking-widest">Execution Notes</label>
              <input
                type="text"
                placeholder="Reason for manual system override..."
                value={adjNotes}
                onChange={e => setAdjNotes(e.target.value)}
                className="bg-[#12141f] border border-surface-border rounded py-2 px-3 text-white font-mono text-sm focus:outline-none focus:border-brand focus:ring-1 focus:ring-brand transition-all w-full"
              />
            </div>
            <button onClick={handleAdjust} disabled={mutation.isPending || !adjAmount} className="btn-primary py-2 px-6 w-full md:w-auto flex items-center justify-center">
              {mutation.isPending ? <RefreshCw size={16} className="animate-spin" /> : <span className="mono text-xs uppercase tracking-widest font-bold">Inject</span>}
            </button>
          </div>
        )}
      </div>

      {/* Transaction Data Grid */}
      <div className="flex-1 flex flex-col space-y-3 min-h-[400px]">
        <div className="flex items-center justify-between px-1">
          <div className="text-xs text-brand mono font-bold uppercase tracking-widest">System Transaction Log</div>
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
          {entriesLoading ? (
            <div className="flex-1 flex flex-col items-center justify-center text-gray-500 gap-3">
               <Activity className="animate-pulse-slow text-brand" size={32} />
               <span className="mono text-xs uppercase tracking-widest">Retrieving Ledger Blocks...</span>
            </div>
          ) : entries.length === 0 ? (
            <div className="flex-1 flex items-center justify-center text-gray-500 mono text-sm uppercase tracking-widest">
              No Transaction Data Found
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
            <span>{table.getRowModel().rows.length} Blocks Rendered</span>
            <span>Integrity: <span className="text-system-online">Verified</span></span>
          </div>
        </div>
      </div>
    </div>
  )
}