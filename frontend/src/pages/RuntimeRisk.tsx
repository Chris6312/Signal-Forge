import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchRuntime, fetchMarketStatus, patchRuntime, haltTrading, resumeTrading, resetPaperData } from '@/api/endpoints'
import type { MarketStatusResponse } from '@/api/types'
import StatusBadge from '@/components/StatusBadge'
import { RefreshCw, ShieldAlert, ShieldCheck, Settings, FlaskConical, Zap, Clock, Trash2 } from 'lucide-react'
import { formatET, relativeTime } from '@/utils/time'

interface RuntimeState {
  status: string
  trading_enabled: boolean
  crypto_trading_enabled: boolean
  stock_trading_enabled: boolean
  trading_mode: string
  risk_per_trade_pct: number
  max_crypto_positions: number
  max_stock_positions: number
  crypto_monitor: string
  stock_monitor: string
  crypto_exit_worker: string
  stock_exit_worker: string
  discord_listener: string
  last_heartbeat: string | null
  started_at: string | null
}

/** Map raw worker status → display status for stock workers based on current market window. */
function stockStatus(raw: string, ms: MarketStatusResponse['status']): string {
  if (ms === 'closed')     return 'paused'
  if (ms === 'pre_market') return 'pre-market'
  if (ms === 'eod')        return 'eod'
  return raw
}

export default function RuntimeRisk() {
  const qc = useQueryClient()
  const [adminToken, setAdminToken] = useState('')
  const [maxCrypto, setMaxCrypto] = useState('')
  const [maxStock, setMaxStock] = useState('')
  const [cryptoSeed, setCryptoSeed] = useState('')
  const [stockSeed, setStockSeed] = useState('')
  const [confirmReset, setConfirmReset] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const { data, isLoading, refetch } = useQuery<RuntimeState>({
    queryKey: ['runtime'],
    queryFn: fetchRuntime,
    refetchInterval: 10000,
  })

  const { data: marketData } = useQuery<MarketStatusResponse>({
    queryKey: ['market-status'],
    queryFn: fetchMarketStatus,
    refetchInterval: 60_000,
    staleTime: 30_000,
  })

  const ms = marketData?.status ?? 'open'

  const mutateHalt = useMutation({
    mutationFn: () => haltTrading(adminToken),
    onSuccess: () => { setSuccess('Trading halted'); qc.invalidateQueries({ queryKey: ['runtime'] }) },
    onError: () => setError('Invalid admin token or request failed'),
  })

  const mutateResume = useMutation({
    mutationFn: () => resumeTrading(adminToken),
    onSuccess: () => { setSuccess('Trading resumed'); qc.invalidateQueries({ queryKey: ['runtime'] }) },
    onError: () => setError('Invalid admin token or request failed'),
  })

  const mutateUpdate = useMutation({
    mutationFn: (body: object) => patchRuntime(body, adminToken),
    onSuccess: () => { setSuccess('Settings updated'); qc.invalidateQueries({ queryKey: ['runtime'] }) },
    onError: () => setError('Invalid admin token or request failed'),
  })

  const mutateReset = useMutation({
    mutationFn: () => resetPaperData(
      adminToken,
      parseFloat(cryptoSeed) || 0,
      parseFloat(stockSeed)  || 0,
    ),
    onSuccess: (d) => {
      setSuccess(`Reset complete — crypto $${d.crypto_balance.toFixed(2)} | stock $${d.stock_balance.toFixed(2)}`)
      setConfirmReset(false)
      qc.invalidateQueries({ queryKey: ['runtime'] })
      qc.invalidateQueries({ queryKey: ['dashboard'] })
    },
    onError: () => setError('Reset failed — check admin token'),
  })

  const handleUpdate = () => {
    setError(null)
    setSuccess(null)
    const body: Record<string, number> = {}
    if (maxCrypto) body.max_crypto_positions = parseInt(maxCrypto)
    if (maxStock) body.max_stock_positions = parseInt(maxStock)
    if (Object.keys(body).length === 0) return
    mutateUpdate.mutate(body)
  }

  const workers = data ? [
    { key: 'crypto_monitor',    label: 'Crypto Monitor',     status: data.crypto_monitor,                  isStock: false },
    { key: 'stock_monitor',     label: 'Stock Monitor',      status: stockStatus(data.stock_monitor, ms),   isStock: true  },
    { key: 'crypto_exit_worker',label: 'Crypto Exit Worker', status: data.crypto_exit_worker,              isStock: false },
    { key: 'stock_exit_worker', label: 'Stock Exit Worker',  status: stockStatus(data.stock_exit_worker, ms), isStock: true },
    { key: 'discord_listener',  label: 'Discord Listener',   status: data.discord_listener,                isStock: false },
  ] : []

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Runtime & Risk</h1>
          <p className="text-sm text-gray-500 mt-1">System controls and safety configuration</p>
        </div>
        <button onClick={() => refetch()} className="btn-ghost flex items-center gap-1.5">
          <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="card border-red-500/30 bg-red-500/10 text-red-400 text-sm">{error}</div>
      )}
      {success && (
        <div className="card border-emerald-500/30 bg-emerald-500/10 text-emerald-400 text-sm">{success}</div>
      )}

      {/* System Overview */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="card space-y-4">
          <div className="text-xs text-gray-400 uppercase tracking-wider font-medium flex items-center gap-2">
            <Settings size={12} />
            System Status
          </div>
          {isLoading ? (
            <div className="text-gray-500 text-sm">Loading…</div>
          ) : data ? (
            <div className="space-y-3 text-sm">
              <Row label="Status" value={<StatusBadge status={data.status} />} />
              <Row label="Mode" value={
                <span className={`text-sm font-semibold flex items-center gap-1.5 ${
                  data.trading_mode === 'live' ? 'text-emerald-400' : 'text-amber-400'
                }`}>
                  {data.trading_mode === 'live' ? <Zap size={13} /> : <FlaskConical size={13} />}
                  {data.trading_mode?.toUpperCase() ?? 'PAPER'}
                </span>
              } />
              <Row label="Risk / Trade" value={<span className="mono text-white">{((data.risk_per_trade_pct ?? 0.02) * 100).toFixed(1)}%</span>} />
              <Row label="Trading" value={<StatusBadge status={data.trading_enabled ? 'ACTIVE' : 'INACTIVE'} />} />
              <Row label="Crypto Trading" value={<StatusBadge status={data.crypto_trading_enabled ? 'ACTIVE' : 'INACTIVE'} />} />
              <Row label="Stock Trading" value={<StatusBadge status={
                !data.stock_trading_enabled ? 'INACTIVE'
                : ms === 'closed'     ? 'paused'
                : ms === 'pre_market' ? 'pre-market'
                : ms === 'eod'        ? 'eod'
                : 'ACTIVE'
              } />} />
              <Row label="Max Crypto Positions" value={<span className="mono text-white">{data.max_crypto_positions}</span>} />
              <Row label="Max Stock Positions" value={<span className="mono text-white">{data.max_stock_positions}</span>} />
              {data.started_at && (
                <Row label="Started" value={<span className="text-gray-400 text-xs" title={relativeTime(data.started_at)}>{formatET(data.started_at)}</span>} />
              )}
              {data.last_heartbeat && (
                <Row label="Last Heartbeat" value={<span className="text-gray-400 text-xs" title={relativeTime(data.last_heartbeat)}>{formatET(data.last_heartbeat)}</span>} />
              )}
            </div>
          ) : null}
        </div>

        <div className="card space-y-4">
          <div className="text-xs text-gray-400 uppercase tracking-wider font-medium">Worker Status</div>

          {/* Market-hours context banners */}
          {ms === 'closed' && (
            <div className="flex items-center gap-2 text-xs text-slate-400 bg-slate-500/10 border border-slate-500/20 rounded-lg px-3 py-2">
              <Clock size={12} className="shrink-0" />
              <span>Stock workers paused — NYSE closed.&nbsp;
                <span className="font-mono">{marketData?.is_trading_day ? 'Resumes 9:15 AM ET' : 'Next trading day 9:15 AM ET'}</span>
              </span>
            </div>
          )}
          {ms === 'pre_market' && (
            <div className="flex items-center gap-2 text-xs text-sky-400 bg-sky-500/10 border border-sky-500/20 rounded-lg px-3 py-2">
              <Clock size={12} className="shrink-0" />
              Pre-market window — candles loading, signals prepping.
              <span className="font-mono ml-auto">Entries open 9:30 AM ET</span>
            </div>
          )}
          {ms === 'eod' && (
            <div className="flex items-center gap-2 text-xs text-amber-400 bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2">
              <Clock size={12} className="shrink-0" />
              EOD window — stock entries blocked, exits active.
              <span className="font-mono ml-auto">Closes 4:00 PM ET</span>
            </div>
          )}

          <div className="space-y-2">
            {workers.map(w => (
              <div key={w.key} className="flex items-center justify-between text-sm">
                <span className={w.isStock && ms !== 'open' ? 'text-gray-500' : 'text-gray-400'}>
                  {w.label}
                </span>
                <StatusBadge status={w.status} />
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Controls */}
      <div className="card space-y-5">
        <div className="text-xs text-gray-400 uppercase tracking-wider font-medium flex items-center gap-2">
          <ShieldAlert size={12} />
          Admin Controls
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-xs text-gray-500">Admin Token</label>
          <input
            type="password"
            value={adminToken}
            onChange={e => setAdminToken(e.target.value)}
            placeholder="Enter admin token"
            className="bg-surface border border-surface-border rounded-lg px-3 py-2 text-sm mono text-white focus:outline-none focus:border-brand w-72"
          />
        </div>

        {/* Halt / Resume */}
        <div className="flex gap-3 flex-wrap">
          <button
            onClick={() => { setError(null); setSuccess(null); mutateHalt.mutate() }}
            disabled={!adminToken || mutateHalt.isPending}
            className="flex items-center gap-2 bg-red-600/20 hover:bg-red-600/30 text-red-400 border border-red-600/30 px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-40"
          >
            <ShieldAlert size={14} />
            {mutateHalt.isPending ? 'Halting…' : 'Halt All Trading'}
          </button>
          <button
            onClick={() => { setError(null); setSuccess(null); mutateResume.mutate() }}
            disabled={!adminToken || mutateResume.isPending}
            className="flex items-center gap-2 bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-400 border border-emerald-600/30 px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-40"
          >
            <ShieldCheck size={14} />
            {mutateResume.isPending ? 'Resuming…' : 'Resume Trading'}
          </button>
        </div>

        {/* Paper / Live mode */}
        <div className="border-t border-surface-border pt-5 space-y-3">
          <div className="text-xs text-gray-500">Trading Mode</div>
          <div className="flex gap-2">
            <button
              onClick={() => { setError(null); setSuccess(null); mutateUpdate.mutate({ trading_mode: 'paper' }) }}
              disabled={!adminToken || mutateUpdate.isPending || data?.trading_mode === 'paper'}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors border ${
                data?.trading_mode === 'paper'
                  ? 'bg-amber-500/20 text-amber-400 border-amber-500/30 cursor-default'
                  : 'bg-surface text-gray-400 border-surface-border hover:text-white disabled:opacity-40'
              }`}
            >
              <FlaskConical size={14} />
              Paper
            </button>
            <button
              onClick={() => { setError(null); setSuccess(null); mutateUpdate.mutate({ trading_mode: 'live' }) }}
              disabled={!adminToken || mutateUpdate.isPending || data?.trading_mode === 'live'}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors border ${
                data?.trading_mode === 'live'
                  ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30 cursor-default'
                  : 'bg-surface text-gray-400 border-surface-border hover:text-white disabled:opacity-40'
              }`}
            >
              <Zap size={14} />
              Live
            </button>
          </div>
        </div>

        {/* Settings */}
        <div className="border-t border-surface-border pt-5 space-y-4">
          <div className="text-xs text-gray-500">Position Limits</div>
          <div className="flex gap-4 flex-wrap items-end">
            <div className="flex flex-col gap-1">
              <label className="text-xs text-gray-500">Max Crypto Positions</label>
              <input
                type="number"
                value={maxCrypto}
                onChange={e => setMaxCrypto(e.target.value)}
                placeholder={String(data?.max_crypto_positions ?? 5)}
                className="bg-surface border border-surface-border rounded-lg px-3 py-2 text-sm mono text-white focus:outline-none focus:border-brand w-28"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs text-gray-500">Max Stock Positions</label>
              <input
                type="number"
                value={maxStock}
                onChange={e => setMaxStock(e.target.value)}
                placeholder={String(data?.max_stock_positions ?? 5)}
                className="bg-surface border border-surface-border rounded-lg px-3 py-2 text-sm mono text-white focus:outline-none focus:border-brand w-28"
              />
            </div>
            <button
              onClick={handleUpdate}
              disabled={!adminToken || mutateUpdate.isPending}
              className="btn-primary disabled:opacity-40"
            >
              {mutateUpdate.isPending ? 'Saving…' : 'Save Settings'}
            </button>
          </div>
        </div>

        {/* Reset Paper Data */}
        <div className="border-t border-surface-border pt-5 space-y-3">
          <div className="text-xs text-red-400 uppercase tracking-wider font-medium flex items-center gap-2">
            <Trash2 size={12} />
            Danger Zone — Reset Paper Data
          </div>
          <p className="text-xs text-gray-500">
            Permanently deletes all positions, orders, ledger entries and audit events.
            Watchlist is preserved. Set seed balances below (leave blank to start at $0).
          </p>
          <div className="flex gap-4 flex-wrap items-end">
            <div className="flex flex-col gap-1">
              <label className="text-xs text-gray-500">Crypto Seed ($)</label>
              <input
                type="number"
                min="0"
                value={cryptoSeed}
                onChange={e => setCryptoSeed(e.target.value)}
                placeholder="0.00"
                className="bg-surface border border-surface-border rounded-lg px-3 py-2 text-sm mono text-white focus:outline-none focus:border-brand w-28"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs text-gray-500">Stock Seed ($)</label>
              <input
                type="number"
                min="0"
                value={stockSeed}
                onChange={e => setStockSeed(e.target.value)}
                placeholder="0.00"
                className="bg-surface border border-surface-border rounded-lg px-3 py-2 text-sm mono text-white focus:outline-none focus:border-brand w-28"
              />
            </div>
          </div>
          {!confirmReset ? (
            <button
              onClick={() => setConfirmReset(true)}
              disabled={!adminToken}
              className="flex items-center gap-2 bg-red-600/20 hover:bg-red-600/30 text-red-400 border border-red-600/30 px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-40"
            >
              <Trash2 size={14} />
              Reset All Paper Data
            </button>
          ) : (
            <div className="flex items-center gap-3 flex-wrap">
              <span className="text-xs text-red-400">This cannot be undone. Are you sure?</span>
              <button
                onClick={() => { setError(null); setSuccess(null); mutateReset.mutate() }}
                disabled={mutateReset.isPending}
                className="flex items-center gap-2 bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-40"
              >
                <Trash2 size={14} />
                {mutateReset.isPending ? 'Resetting…' : 'Yes, Reset Everything'}
              </button>
              <button
                onClick={() => setConfirmReset(false)}
                className="text-xs text-gray-500 hover:text-white transition-colors px-2 py-1"
              >
                Cancel
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-gray-500">{label}</span>
      {value}
    </div>
  )
}
