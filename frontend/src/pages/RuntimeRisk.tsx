import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchRuntime, fetchMarketStatus, patchRuntime, haltTrading, resumeTrading, resetPaperData } from '@/api/endpoints'
import type { MarketStatusResponse } from '@/api/types'
import StatusBadge from '@/components/StatusBadge'
import { RefreshCw, ShieldAlert, ShieldCheck, Settings, FlaskConical, Zap, Clock, Trash2, Cpu, Activity, Server } from 'lucide-react'
import { formatET } from '@/utils/time'
import clsx from 'clsx'

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
  const [sysLog, setSysLog] = useState<{ message: string; type: 'error' | 'success' } | null>(null)

  const { data, isLoading, refetch, isRefetching } = useQuery<RuntimeState>({
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

  const showSysLog = (message: string, type: 'error' | 'success') => {
    setSysLog({ message, type })
    setTimeout(() => setSysLog(null), 5000)
  }

  const mutateHalt = useMutation({
    mutationFn: () => haltTrading(adminToken),
    onSuccess: () => { showSysLog('GLOBAL HALT INITIATED', 'success'); qc.invalidateQueries({ queryKey: ['runtime'] }) },
    onError: () => showSysLog('INVALID TOKEN OR UPLINK FAILURE', 'error'),
  })

  const mutateResume = useMutation({
    mutationFn: () => resumeTrading(adminToken),
    onSuccess: () => { showSysLog('SYSTEMS RESUMED', 'success'); qc.invalidateQueries({ queryKey: ['runtime'] }) },
    onError: () => showSysLog('INVALID TOKEN OR UPLINK FAILURE', 'error'),
  })

  const mutateUpdate = useMutation({
    mutationFn: (body: object) => patchRuntime(body, adminToken),
    onSuccess: () => { showSysLog('CONFIG OVERRIDE ACCEPTED', 'success'); qc.invalidateQueries({ queryKey: ['runtime'] }) },
    onError: () => showSysLog('INVALID TOKEN OR UPLINK FAILURE', 'error'),
  })

  const mutateReset = useMutation({
    mutationFn: () => resetPaperData(
      adminToken,
      parseFloat(cryptoSeed) || 0,
      parseFloat(stockSeed)  || 0,
    ),
    onSuccess: (d) => {
      showSysLog(`PAPER PURGE COMPLETE [ C_BAL: $${d.crypto_balance.toFixed(2)} | S_BAL: $${d.stock_balance.toFixed(2)} ]`, 'success')
      setConfirmReset(false)
      qc.invalidateQueries()
    },
    onError: () => showSysLog('PURGE REJECTED: CHECK AUTH', 'error'),
  })

  const handleUpdate = () => {
    const body: Record<string, number> = {}
    if (maxCrypto) body.max_crypto_positions = parseInt(maxCrypto)
    if (maxStock) body.max_stock_positions = parseInt(maxStock)
    if (Object.keys(body).length === 0) return
    mutateUpdate.mutate(body)
  }

  const workers = data ? [
    { key: 'crypto_monitor',    label: 'CRYPTO_MON',     status: data.crypto_monitor,                  isStock: false },
    { key: 'stock_monitor',     label: 'STOCK_MON',      status: stockStatus(data.stock_monitor, ms),   isStock: true  },
    { key: 'crypto_exit_worker',label: 'CRYPTO_EXIT',    status: data.crypto_exit_worker,              isStock: false },
    { key: 'stock_exit_worker', label: 'STOCK_EXIT',     status: stockStatus(data.stock_exit_worker, ms), isStock: true },
    { key: 'discord_listener',  label: 'DISCORD_IO',     status: data.discord_listener,                isStock: false },
  ] : []

  return (
    <div className="space-y-6 max-w-[1600px] mx-auto pb-10 h-full flex flex-col">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 border-b border-surface-border pb-4 shrink-0">
        <div>
          <h1 className="text-3xl font-bold text-white tracking-tight flex items-center gap-3">
            <Cpu className="text-brand" /> 
            Engine Config
          </h1>
          <div className="flex items-center gap-3 mt-2 mono text-xs text-gray-500">
            <span>RUNTIME_PARAMETERS</span>
            <span>|</span>
            <span className="text-brand">SYSTEM_LEVEL_ACCESS</span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={() => refetch()} className="btn-ghost flex items-center gap-2 px-3">
            <RefreshCw size={14} className={isLoading || isRefetching ? 'animate-spin text-brand' : ''} />
            <span className="mono text-xs uppercase tracking-wider">Sync State</span>
          </button>
        </div>
      </div>

      {/* Ephemeral System Messages */}
      {sysLog && (
        <div className={clsx(
          "px-4 py-3 rounded-lg border flex items-center gap-3 font-mono text-xs uppercase tracking-widest shadow-card-inset animate-in fade-in slide-in-from-top-2 duration-300",
          sysLog.type === 'error' ? "bg-system-offline/10 border-system-offline text-system-offline drop-shadow-[0_0_8px_rgba(239,68,68,0.5)]" : "bg-system-online/10 border-system-online text-system-online drop-shadow-[0_0_8px_rgba(16,185,129,0.5)]"
        )}>
          {sysLog.type === 'error' ? <ShieldAlert size={16} /> : <ShieldCheck size={16} />}
          {sysLog.message}
        </div>
      )}

      {/* Grid Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        
        {/* Core Telemetry Panel */}
        <div className="card space-y-4 relative overflow-hidden group">
          <div className="absolute inset-0 bg-gradient-to-br from-brand/5 to-surface opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none"></div>
          <div className="text-xs text-brand mono font-bold uppercase tracking-widest flex items-center justify-between border-b border-surface-border pb-3 relative z-10">
            <div className="flex items-center gap-2">
              <Settings size={14} /> Core Telemetry
            </div>
            {isLoading && <Activity size={14} className="animate-pulse" />}
          </div>
          
          <div className="space-y-4 relative z-10">
            <Row label="Master Engine" value={<StatusBadge status={data?.status ?? 'UNKNOWN'} />} />
            
            <Row label="Operation Mode" value={
              <span className={clsx(
                "text-xs font-mono font-bold tracking-widest uppercase flex items-center gap-1.5 border px-2 py-0.5 rounded shadow-card-inset",
                data?.trading_mode === 'live' 
                  ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30 shadow-[0_0_10px_rgba(16,185,129,0.2)]' 
                  : 'bg-amber-500/10 text-amber-400 border-amber-500/30'
              )}>
                {data?.trading_mode === 'live' ? <Zap size={12} /> : <FlaskConical size={12} />}
                {data?.trading_mode ?? 'PAPER'}
              </span>
            } />
            
            <Row label="Risk Threshold (Per Vector)" value={<span className="mono text-white bg-[#12141f] border border-surface-border px-2 py-0.5 rounded shadow-card-inset">{((data?.risk_per_trade_pct ?? 0.02) * 100).toFixed(1)}%</span>} />
            <Row label="Global Trading" value={<StatusBadge status={data?.trading_enabled ? 'ACTIVE' : 'INACTIVE'} />} />
            <Row label="Node_A Execution (Crypto)" value={<StatusBadge status={data?.crypto_trading_enabled ? 'ACTIVE' : 'INACTIVE'} />} />
            
            <Row label="Node_B Execution (Stock)" value={<StatusBadge status={
              !data?.stock_trading_enabled ? 'INACTIVE'
              : ms === 'closed'     ? 'paused'
              : ms === 'pre_market' ? 'pre-market'
              : ms === 'eod'        ? 'eod'
              : 'ACTIVE'
            } />} />
            
            <div className="grid grid-cols-2 gap-4 pt-2">
              <div className="bg-[#12141f] border border-surface-border rounded-lg p-3 text-center shadow-card-inset">
                <div className="text-[10px] text-gray-500 mono uppercase mb-1">Max Crypto Vectors</div>
                <div className="text-xl font-mono text-white drop-shadow-[0_0_5px_rgba(255,255,255,0.5)]">{data?.max_crypto_positions ?? '--'}</div>
              </div>
              <div className="bg-[#12141f] border border-surface-border rounded-lg p-3 text-center shadow-card-inset">
                <div className="text-[10px] text-gray-500 mono uppercase mb-1">Max Stock Vectors</div>
                <div className="text-xl font-mono text-white drop-shadow-[0_0_5px_rgba(255,255,255,0.5)]">{data?.max_stock_positions ?? '--'}</div>
              </div>
            </div>

            {data?.last_heartbeat && (
              <div className="flex items-center justify-between text-[10px] mono text-gray-600 border-t border-surface-border pt-3">
                <span>LAST_UPLINK_HEARTBEAT</span>
                <span className="text-brand flex items-center gap-1"><Activity size={10} className="animate-pulse" /> {formatET(data.last_heartbeat)}</span>
              </div>
            )}
          </div>
        </div>

        {/* Worker Node Status Rack */}
        <div className="card space-y-4 bg-[#0d0f18] border-brand/20 shadow-card-inset flex flex-col">
          <div className="text-xs text-gray-400 mono font-bold uppercase tracking-widest flex items-center gap-2 border-b border-surface-border pb-3">
            <Server size={14} /> Active Node Rack
          </div>

          {/* Market Window Alerts */}
          {ms === 'closed' && (
            <div className="flex items-center gap-3 text-[10px] mono text-slate-400 bg-slate-500/10 border border-slate-500/30 rounded-lg px-4 py-2.5 uppercase tracking-widest shadow-card-inset shrink-0">
              <Clock size={14} className="shrink-0 text-slate-300" />
              <span>Node_B (Stock) Paused. <span className="text-white ml-2">[{marketData?.is_trading_day ? 'Resumes 09:15 ET' : 'Next Day 09:15 ET'}]</span></span>
            </div>
          )}
          {ms === 'pre_market' && (
            <div className="flex items-center gap-3 text-[10px] mono text-sky-400 bg-sky-500/10 border border-sky-500/30 rounded-lg px-4 py-2.5 uppercase tracking-widest shadow-card-inset shrink-0">
              <Activity size={14} className="shrink-0 text-sky-300 animate-pulse" />
              <span>Pre-Market Analysis. <span className="text-white ml-2">[Entries unlock 09:30 ET]</span></span>
            </div>
          )}
          {ms === 'eod' && (
            <div className="flex items-center gap-3 text-[10px] mono text-amber-400 bg-amber-500/10 border border-amber-500/30 rounded-lg px-4 py-2.5 uppercase tracking-widest shadow-card-inset shrink-0">
              <ShieldAlert size={14} className="shrink-0 text-amber-300" />
              <span>EOD Window Active. Entries Blocked. <span className="text-white ml-2">[Closes 16:00 ET]</span></span>
            </div>
          )}

          <div className="flex-1 flex flex-col gap-2.5 justify-center">
            {workers.map(w => {
              const isOnline = w.status === 'online' || w.status === 'running'
              return (
                <div key={w.key} className={clsx(
                  "flex items-center justify-between p-3 rounded-lg border transition-all",
                  isOnline ? "bg-system-online/5 border-system-online/20" : "bg-surface border-surface-border"
                )}>
                  <div className="flex items-center gap-3">
                    <Server size={14} className={isOnline ? 'text-system-online drop-shadow-[0_0_5px_rgba(16,185,129,0.8)]' : 'text-gray-600'} />
                    <span className={clsx("text-xs font-mono font-bold tracking-widest uppercase", w.isStock && ms !== 'open' ? 'text-gray-500' : 'text-gray-300')}>
                      {w.label}
                    </span>
                  </div>
                  <StatusBadge status={w.status} />
                </div>
              )
            })}
          </div>
        </div>

        {/* Command Controls */}
        <div className="lg:col-span-2 card space-y-6 border-brand/40 shadow-[inset_0_1px_0_0_rgba(255,255,255,0.05),0_0_30px_-10px_rgba(99,102,241,0.15)] relative overflow-hidden">
          <div className="absolute top-0 right-0 p-4 opacity-5 pointer-events-none">
            <ShieldAlert size={100} />
          </div>
          
          <div className="text-xs text-brand mono font-bold uppercase tracking-widest flex items-center gap-2 border-b border-surface-border pb-3 relative z-10">
            <ShieldAlert size={14} /> Master Command Console
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8 relative z-10">
            
            {/* Auth Input */}
            <div className="md:col-span-3 lg:col-span-1 space-y-4">
              <div className="space-y-1.5">
                <label className="text-[10px] text-gray-500 mono uppercase tracking-widest block">Authorization Required</label>
                <input
                  type="password"
                  value={adminToken}
                  onChange={e => setAdminToken(e.target.value)}
                  placeholder="Enter x-admin-token"
                  className="bg-[#0b0c13] border border-brand/50 rounded py-2.5 px-4 text-white font-mono text-sm focus:outline-none focus:ring-1 focus:ring-brand shadow-[0_0_10px_rgba(99,102,241,0.2)] w-full transition-all"
                  autoComplete="off"
                />
              </div>

              {/* Master Halt / Resume */}
              <div className="space-y-2">
                <label className="text-[10px] text-gray-500 mono uppercase tracking-widest block">Global Execution Switch</label>
                <div className="flex gap-2">
                  <button
                    onClick={() => mutateHalt.mutate()}
                    disabled={!adminToken || mutateHalt.isPending}
                    className="flex-1 flex items-center justify-center gap-2 bg-system-offline/20 hover:bg-system-offline/40 text-system-offline border border-system-offline/50 py-2 rounded text-xs font-mono font-bold tracking-widest transition-all disabled:opacity-30 shadow-[0_0_15px_-5px_rgba(239,68,68,0.4)] hover:shadow-[0_0_20px_rgba(239,68,68,0.6)] uppercase"
                  >
                    {mutateHalt.isPending ? <Activity size={14} className="animate-pulse" /> : <ShieldAlert size={14} />}
                    Halt All
                  </button>
                  <button
                    onClick={() => mutateResume.mutate()}
                    disabled={!adminToken || mutateResume.isPending}
                    className="flex-1 flex items-center justify-center gap-2 bg-system-online/20 hover:bg-system-online/40 text-system-online border border-system-online/50 py-2 rounded text-xs font-mono font-bold tracking-widest transition-all disabled:opacity-30 shadow-[0_0_15px_-5px_rgba(16,185,129,0.4)] hover:shadow-[0_0_20px_rgba(16,185,129,0.6)] uppercase"
                  >
                    {mutateResume.isPending ? <Activity size={14} className="animate-pulse" /> : <ShieldCheck size={14} />}
                    Resume
                  </button>
                </div>
              </div>
            </div>

            <div className="md:col-span-2 grid grid-cols-1 md:grid-cols-2 gap-6 pl-0 md:pl-6 border-t md:border-t-0 md:border-l border-surface-border pt-6 md:pt-0">
              
              {/* Configuration Override */}
              <div className="space-y-4">
                <label className="text-[10px] text-gray-500 mono uppercase tracking-widest block">Parameter Override</label>
                
                <div className="bg-[#12141f] border border-surface-border rounded p-3 space-y-3 shadow-card-inset">
                  <div className="flex gap-2 bg-surface p-1 rounded border border-surface-border">
                    <button
                      onClick={() => mutateUpdate.mutate({ trading_mode: 'paper' })}
                      disabled={!adminToken || mutateUpdate.isPending || data?.trading_mode === 'paper'}
                      className={clsx(
                        "flex-1 flex items-center justify-center gap-2 py-1.5 rounded text-[10px] font-mono uppercase tracking-widest transition-all",
                        data?.trading_mode === 'paper' ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30' : 'text-gray-500 hover:text-gray-300 disabled:opacity-30'
                      )}
                    >
                      <FlaskConical size={12} /> Paper
                    </button>
                    <button
                      onClick={() => mutateUpdate.mutate({ trading_mode: 'live' })}
                      disabled={!adminToken || mutateUpdate.isPending || data?.trading_mode === 'live'}
                      className={clsx(
                        "flex-1 flex items-center justify-center gap-2 py-1.5 rounded text-[10px] font-mono uppercase tracking-widest transition-all",
                        data?.trading_mode === 'live' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' : 'text-gray-500 hover:text-gray-300 disabled:opacity-30'
                      )}
                    >
                      <Zap size={12} /> Live
                    </button>
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <div className="space-y-1">
                      <label className="text-[9px] text-gray-500 mono">MAX_CRYPTO</label>
                      <input type="number" value={maxCrypto} onChange={e => setMaxCrypto(e.target.value)} placeholder={String(data?.max_crypto_positions ?? 5)} className="w-full bg-surface border border-surface-border rounded py-1.5 px-2 text-white font-mono text-xs focus:outline-none focus:border-brand transition-all" />
                    </div>
                    <div className="space-y-1">
                      <label className="text-[9px] text-gray-500 mono">MAX_STOCK</label>
                      <input type="number" value={maxStock} onChange={e => setMaxStock(e.target.value)} placeholder={String(data?.max_stock_positions ?? 5)} className="w-full bg-surface border border-surface-border rounded py-1.5 px-2 text-white font-mono text-xs focus:outline-none focus:border-brand transition-all" />
                    </div>
                  </div>
                  
                  <button onClick={handleUpdate} disabled={!adminToken || mutateUpdate.isPending} className="w-full btn-primary py-1.5 text-xs font-mono uppercase tracking-widest disabled:opacity-30">
                    Apply Override
                  </button>
                </div>
              </div>

              {/* Danger Zone: Purge Data */}
              <div className="space-y-4">
                <label className="text-[10px] text-system-offline mono uppercase tracking-widest flex items-center gap-1.5"><Trash2 size={12}/> Critical: Data Purge</label>
                
                <div className="bg-system-offline/5 border border-system-offline/20 rounded p-3 space-y-3 relative overflow-hidden group">
                  <div className="absolute inset-0 opacity-10 bg-[repeating-linear-gradient(45deg,transparent,transparent_8px,#ef4444_8px,#ef4444_16px)] pointer-events-none group-hover:opacity-20 transition-opacity"></div>
                  
                  <p className="text-[9px] text-red-300/80 mono uppercase leading-tight relative z-10">Permanently clears ledger, orders, and audit. Seeds below.</p>
                  
                  <div className="grid grid-cols-2 gap-2 relative z-10">
                    <div className="space-y-1">
                      <label className="text-[9px] text-red-400 mono">SEED_CRYPTO ($)</label>
                      <input type="number" min="0" value={cryptoSeed} onChange={e => setCryptoSeed(e.target.value)} placeholder="0.00" className="w-full bg-surface border border-red-500/30 rounded py-1.5 px-2 text-white font-mono text-xs focus:outline-none focus:border-red-500 transition-all" />
                    </div>
                    <div className="space-y-1">
                      <label className="text-[9px] text-red-400 mono">SEED_STOCK ($)</label>
                      <input type="number" min="0" value={stockSeed} onChange={e => setStockSeed(e.target.value)} placeholder="0.00" className="w-full bg-surface border border-red-500/30 rounded py-1.5 px-2 text-white font-mono text-xs focus:outline-none focus:border-red-500 transition-all" />
                    </div>
                  </div>
                  
                  {!confirmReset ? (
                    <button onClick={() => setConfirmReset(true)} disabled={!adminToken} className="w-full py-1.5 text-[10px] font-mono font-bold tracking-widest uppercase text-system-offline border border-system-offline/30 hover:bg-system-offline hover:text-white transition-all rounded disabled:opacity-30 relative z-10 bg-[#0b0c13]">
                      Initiate Purge Sequence
                    </button>
                  ) : (
                    <div className="flex gap-2 relative z-10">
                      <button onClick={() => mutateReset.mutate()} disabled={mutateReset.isPending} className="flex-1 py-1.5 text-[10px] font-mono font-bold tracking-widest uppercase text-white bg-system-offline hover:bg-red-600 transition-all rounded disabled:opacity-30 shadow-[0_0_15px_rgba(239,68,68,0.5)]">
                        {mutateReset.isPending ? 'Purging...' : 'Confirm Purge'}
                      </button>
                      <button onClick={() => setConfirmReset(false)} className="px-3 py-1.5 text-[10px] font-mono tracking-widest uppercase text-gray-400 hover:text-white bg-surface border border-surface-border rounded">
                        Abort
                      </button>
                    </div>
                  )}
                </div>
              </div>
              
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between items-center group">
      <span className="text-gray-500 mono text-xs uppercase tracking-wider group-hover:text-gray-400 transition-colors">{label}</span>
      <div className="text-right">
        {value}
      </div>
    </div>
  )
}