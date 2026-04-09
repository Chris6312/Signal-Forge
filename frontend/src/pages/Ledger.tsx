import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchLedgerAccounts, fetchLedgerEntries, postAdjustment } from '@/api/endpoints'
import MetricCard from '@/components/MetricCard'
import { RefreshCw, Plus } from 'lucide-react'
import { formatET, relativeTime } from '@/utils/time'

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

export default function Ledger() {
  const qc = useQueryClient()
  const [filterClass, setFilterClass] = useState<string>('')
  const [adjClass, setAdjClass] = useState<'crypto' | 'stock'>('crypto')
  const [adjAmount, setAdjAmount] = useState('')
  const [adjNotes, setAdjNotes] = useState('')
  const [adjOpen, setAdjOpen] = useState(false)

  const params: Record<string, string> = {}
  if (filterClass) params.asset_class = filterClass

  const { data: accounts = [], isLoading: accsLoading, refetch: refetchAccts } = useQuery<LedgerAccount[]>({
    queryKey: ['ledger-accounts'],
    queryFn: fetchLedgerAccounts,
    refetchInterval: 15000,
  })

  const { data: entries = [], isLoading: entriesLoading, refetch: refetchEntries } = useQuery<LedgerEntry[]>({
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
    },
  })

  const handleAdjust = () => {
    const amount = parseFloat(adjAmount)
    if (isNaN(amount)) return
    mutation.mutate({ asset_class: adjClass, amount, notes: adjNotes })
  }

  const cryptoAcct = accounts.find(a => a.asset_class === 'crypto')
  const stockAcct = accounts.find(a => a.asset_class === 'stock')

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Paper Ledger</h1>
          <p className="text-sm text-gray-500 mt-1">Internal financial truth — separate from broker state</p>
        </div>
        <button onClick={() => { refetchAccts(); refetchEntries() }} className="btn-ghost flex items-center gap-1.5">
          <RefreshCw size={14} className={accsLoading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {/* Account summaries */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {[
          { label: 'Crypto (Kraken)', account: cryptoAcct },
          { label: 'Stocks (Tradier)', account: stockAcct },
        ].map(({ label, account }) => (
          <div key={label} className="card space-y-4">
            <div className="text-xs text-gray-400 uppercase tracking-wider font-medium">{label}</div>
            {accsLoading ? (
              <div className="text-gray-500 text-sm">Loading…</div>
            ) : !account ? (
              <div className="text-gray-500 text-sm">No account yet</div>
            ) : (
              <>
                <div className="grid grid-cols-2 gap-3">
                  <MetricCard
                    label="Cash Balance"
                    value={account.cash_balance.toFixed(2)}
                    mono
                  />
                  <MetricCard
                    label="Realized PnL"
                    value={(account.realized_pnl >= 0 ? '+' : '') + account.realized_pnl.toFixed(2)}
                    positive={account.realized_pnl > 0}
                    negative={account.realized_pnl < 0}
                    mono
                  />
                  <MetricCard
                    label="Unrealized PnL"
                    value={(account.unrealized_pnl >= 0 ? '+' : '') + account.unrealized_pnl.toFixed(2)}
                    positive={account.unrealized_pnl > 0}
                    negative={account.unrealized_pnl < 0}
                    mono
                  />
                  <MetricCard label="Total Fees" value={account.fees_total.toFixed(4)} mono />
                </div>
                {account.last_reconciled_at && (
                  <div className="text-xs text-gray-500">
                    Last reconciled: <span title={relativeTime(account.last_reconciled_at)}>{formatET(account.last_reconciled_at)}</span>
                  </div>
                )}
              </>
            )}
          </div>
        ))}
      </div>

      {/* Manual Adjustment */}
      <div className="card space-y-4">
        <button
          className="flex items-center gap-2 text-sm font-medium text-gray-300 w-full"
          onClick={() => setAdjOpen(o => !o)}
        >
          <Plus size={14} className="text-brand" />
          Manual Adjustment
        </button>
        {adjOpen && (
          <div className="flex gap-3 flex-wrap items-end">
            <div className="flex flex-col gap-1">
              <label className="text-xs text-gray-500">Asset Class</label>
              <select
                value={adjClass}
                onChange={e => setAdjClass(e.target.value as 'crypto' | 'stock')}
                className="bg-surface border border-surface-border rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-brand"
              >
                <option value="crypto">Crypto</option>
                <option value="stock">Stock</option>
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs text-gray-500">Amount</label>
              <input
                type="number"
                placeholder="0.00"
                value={adjAmount}
                onChange={e => setAdjAmount(e.target.value)}
                className="bg-surface border border-surface-border rounded-lg px-3 py-2 text-sm mono text-white focus:outline-none focus:border-brand w-32"
              />
            </div>
            <div className="flex flex-col gap-1 flex-1">
              <label className="text-xs text-gray-500">Notes</label>
              <input
                type="text"
                placeholder="Reason for adjustment"
                value={adjNotes}
                onChange={e => setAdjNotes(e.target.value)}
                className="bg-surface border border-surface-border rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-brand w-full"
              />
            </div>
            <button onClick={handleAdjust} disabled={mutation.isPending} className="btn-primary">
              {mutation.isPending ? 'Saving…' : 'Apply'}
            </button>
          </div>
        )}
      </div>

      {/* Ledger Entries */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="text-sm font-medium text-gray-300">Transaction Log</div>
          <div className="flex gap-2">
            {['', 'crypto', 'stock'].map(c => (
              <button
                key={c}
                onClick={() => setFilterClass(c)}
                className={`px-3 py-1 rounded-lg text-xs transition-colors ${
                  filterClass === c ? 'bg-brand text-white' : 'bg-surface-card text-gray-400 hover:text-white'
                }`}
              >
                {c || 'All'}
              </button>
            ))}
          </div>
        </div>
        <div className="card p-0 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-surface-border text-xs text-gray-500 uppercase tracking-wider">
                <th className="text-left px-5 py-3">Time</th>
                <th className="text-left px-5 py-3">Class</th>
                <th className="text-left px-5 py-3">Type</th>
                <th className="text-left px-5 py-3">Symbol</th>
                <th className="text-right px-5 py-3">Amount</th>
                <th className="text-right px-5 py-3">Balance After</th>
                <th className="text-left px-5 py-3">Notes</th>
              </tr>
            </thead>
            <tbody>
              {entriesLoading && (
                <tr><td colSpan={7} className="px-5 py-8 text-center text-gray-500">Loading…</td></tr>
              )}
              {!entriesLoading && entries.length === 0 && (
                <tr><td colSpan={7} className="px-5 py-8 text-center text-gray-500">No entries</td></tr>
              )}
              {entries.map(e => (
                <tr key={e.id} className="border-b border-surface-border/50 table-row-hover">
                  <td className="px-5 py-3 text-gray-400 text-xs whitespace-nowrap">
                    {e.created_at
                      ? <span title={relativeTime(e.created_at)}>
                          {formatET(e.created_at)}
                        </span>
                      : '—'}
                  </td>
                  <td className="px-5 py-3">
                    <span className={`badge ${e.asset_class === 'crypto' ? 'bg-violet-500/20 text-violet-400 border border-violet-500/30' : 'bg-sky-500/20 text-sky-400 border border-sky-500/30'}`}>
                      {e.asset_class}
                    </span>
                  </td>
                  <td className="px-5 py-3 text-xs text-gray-400">{e.entry_type}</td>
                  <td className="px-5 py-3 mono text-white">{e.symbol || '—'}</td>
                  <td className={`px-5 py-3 text-right mono ${e.amount >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    {e.amount >= 0 ? '+' : ''}{e.amount.toFixed(4)}
                  </td>
                  <td className="px-5 py-3 text-right mono text-gray-300">{e.balance_after.toFixed(4)}</td>
                  <td className="px-5 py-3 text-gray-500 text-xs max-w-[200px] truncate">{e.notes || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
