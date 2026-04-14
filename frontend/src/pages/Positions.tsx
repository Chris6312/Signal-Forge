import React, { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table'
import { fetchOpenPositions } from '@/api/endpoints'
import {
  Activity,
  ChevronDown,
  ChevronRight,
  Info,
  RefreshCw,
  Search,
  Shield,
  Target,
  TrendingUp,
  Wallet,
  Zap,
} from 'lucide-react'
import StatusBadge from '@/components/StatusBadge'
import { formatET, relativeTime } from '@/utils/time'
import type { PositionRiskControls } from '@/types/api'
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
  profit_target_1: number | null
  profit_target_2: number | null
  initial_stop: number | null
  current_stop: number | null
  entry_strategy: string | null
  exit_strategy: string | null
  pnl_realized: number | null
  fees_paid: number | null
  max_hold_hours?: number | null
  hours_held?: number | null
  hold_ratio?: number | null
  time_risk_state?: string | null
  regime_at_entry: string | null
  watchlist_source_id?: string | null
  management_policy_version?: string | null
  risk_controls?: PositionRiskControls | null
  milestone_state?: {
    tp1_hit?: boolean
    trail_active?: boolean
    trailing_stop?: number | null
    protection_mode?: string | null
    protected_floor?: number | null
    be_promoted?: boolean
    tp1_price?: number | null
    [key: string]: unknown
  } | null
  frozen_policy?: {
    trail_active?: boolean
    exit_strategy?: string | null
    entry_strategy?: string | null
    initial_stop?: number | null
    profit_target_1?: number | null
    profit_target_2?: number | null
    max_hold_hours?: number | null
    hard_max_hold?: boolean | null
    regime_at_entry?: string | null
    market_regime?: string | null
    watchlist_source_id?: string | null
    management_policy_version?: string | null
    [key: string]: unknown
  } | null
}

type DisplayMetric = {
  label: string
  value: React.ReactNode
  color?: string
  mono?: boolean
}

const columnHelper: any = createColumnHelper()

function formatCurrency(val: number | null | undefined) {
  if (val == null) return '—'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  }).format(val)
}

function formatQuantity(val: number | null | undefined) {
  if (val == null) return '—'
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 8,
  }).format(val)
}

function formatPnL(val: number | null | undefined) {
  if (val == null) return '0.00'
  const formatted = new Intl.NumberFormat('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Math.abs(val))
  return val >= 0 ? `+${formatted}` : `-${formatted}`
}

function formatHoldHours(value: number | null | undefined) {
  if (value == null) return 'Not set'
  const rounded = Math.round(value)
  return `${rounded} hour${rounded === 1 ? '' : 's'}`
}

function formatHeldHours(value: number | null | undefined) {
  if (value == null) return '—'
  const fixed = value.toFixed(1)
  return `${fixed} hour${fixed === '1.0' ? '' : 's'}`
}

function formatPercentage(value: number | null | undefined) {
  if (value == null) return '—'
  return `${Number(value).toFixed(2)}%`
}

function hasRiskControls(riskControls?: PositionRiskControls | null) {
  if (!riskControls) return false
  if (riskControls.risk_multipliers && Object.keys(riskControls.risk_multipliers).length > 0) {
    return true
  }
  return [riskControls.volatility_pct, riskControls.maturity_state, riskControls.regime_state].some(
    (value) => value !== null && value !== undefined && value !== '',
  )
}

function formatRiskMultiplierLabel(key: string) {
  const labels: Record<string, string> = {
    volatility_multiplier: 'Volatility',
    drawdown_multiplier: 'Drawdown',
    cluster_multiplier: 'Cluster',
    concentration_multiplier: 'Concentration',
    portfolio_concentration_multiplier: 'Portfolio Concentration',
    regime_multiplier: 'Regime',
    effective_risk_multiplier: 'Effective Risk',
  }
  return labels[key] || toTitleCase(key)
}

function toTitleCase(value?: string | null) {
  if (!value) return '—'
  return value
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

function yesNo(value?: boolean | null) {
  if (value === true) return 'Yes'
  if (value === false) return 'No'
  return '—'
}

function humanizeProtectionMode(value?: string | null) {
  if (!value) return '—'

  const normalized = value.toLowerCase()
  const labels: Record<string, string> = {
    trail_active: 'Trailing Active',
    break_even: 'Break Even',
    break_even_plus_fees: 'Break Even + Fees',
    protected: 'Protected',
    initial: 'Initial Protection',
    promoted: 'Promoted',
  }

  return labels[normalized] || toTitleCase(value)
}

function holdColorClass(state?: string | null, ratio?: number | null) {
  const normalized = state?.toLowerCase()
  if (normalized === 'green') return 'text-system-online drop-shadow-[0_0_8px_rgba(16,185,129,0.25)]'
  if (normalized === 'yellow') return 'text-amber-300 drop-shadow-[0_0_8px_rgba(245,158,11,0.25)]'
  if (normalized === 'red') return 'text-system-offline drop-shadow-[0_0_8px_rgba(239,68,68,0.3)]'
  if (typeof ratio !== 'number') return 'text-gray-300'
  if (ratio < 0.7) return 'text-system-online drop-shadow-[0_0_8px_rgba(16,185,129,0.25)]'
  if (ratio < 0.9) return 'text-amber-300 drop-shadow-[0_0_8px_rgba(245,158,11,0.25)]'
  return 'text-system-offline drop-shadow-[0_0_8px_rgba(239,68,68,0.3)]'
}

function normalizeStrategyKey(value?: string | null) {
  if (!value) return ''
  return value.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '')
}

function usesProfitTargets(exitStrategy?: string | null) {
  const key = normalizeStrategyKey(exitStrategy)

  if (!key) return true

  const nonTargetStrategies = new Set([
    'range_failure_exit',
  ])

  return !nonTargetStrategies.has(key)
}

function formatTargetValue(
  value: number | null | undefined,
  enabled: boolean,
) {
  if (!enabled) return 'N/A'
  return formatCurrency(value)
}

function formatTpStatus(
  value: boolean,
  enabled: boolean,
) {
  if (!enabled) return 'N/A'
  return value ? 'Hit' : 'Not Hit'
}

function buildMilestoneMetrics(position: Position) {
  const milestone = position.milestone_state || {}
  const frozen = position.frozen_policy || {}
  const effectiveExitStrategy = frozen.exit_strategy || position.exit_strategy || ''
  const targetDriven = usesProfitTargets(effectiveExitStrategy)

  const tp1Hit = targetDriven ? Boolean(milestone.tp1_hit) : false
  const explicitTrailActive = milestone.trail_active === true
  const trailingStopValue =
    milestone.trailing_stop != null
      ? Number(milestone.trailing_stop)
      : null

  const strategyIndicatesDynamicTrail = /dynamic|trail/i.test(String(effectiveExitStrategy))
  const trailActive = Boolean(
    frozen.trail_active ||
      explicitTrailActive ||
      trailingStopValue != null ||
      (tp1Hit && strategyIndicatesDynamicTrail),
  )

  const protectedFloor =
    milestone.protected_floor != null
      ? Number(milestone.protected_floor)
      : position.current_stop ?? position.initial_stop ?? null

  const protectionMode =
    milestone.protection_mode != null
      ? humanizeProtectionMode(String(milestone.protection_mode))
      : trailActive
        ? 'Trailing Active'
        : targetDriven && tp1Hit
          ? 'Protected'
          : 'Initial Protection'

  return {
    targetDriven,
    tp1Hit,
    trailActive,
    trailingStopValue,
    protectedFloor,
    protectionMode,
    promoted: targetDriven ? milestone.be_promoted === true : false,
    tp1Price:
      targetDriven
        ? (
            milestone.tp1_price != null
              ? Number(milestone.tp1_price)
              : position.profit_target_1
          )
        : null,
  }
}

function buildFrozenPolicyMetrics(position: Position) {
  const frozen = position.frozen_policy || {}

  return {
    entryStrategy: frozen.entry_strategy || position.entry_strategy || '—',
    exitStrategy: frozen.exit_strategy || position.exit_strategy || '—',
    initialStop:
      frozen.initial_stop != null
        ? Number(frozen.initial_stop)
        : position.initial_stop,
    profitTarget1:
      frozen.profit_target_1 != null
        ? Number(frozen.profit_target_1)
        : position.profit_target_1,
    profitTarget2:
      frozen.profit_target_2 != null
        ? Number(frozen.profit_target_2)
        : position.profit_target_2,
    maxHoldHours:
      frozen.max_hold_hours != null
        ? Number(frozen.max_hold_hours)
        : position.max_hold_hours,
    hardMaxHold:
      typeof frozen.hard_max_hold === 'boolean'
        ? frozen.hard_max_hold
        : null,
    regimeAtEntry:
      frozen.regime_at_entry || position.regime_at_entry || '—',
    marketRegime:
      frozen.market_regime || 'NEUTRAL',
    watchlistSourceId:
      frozen.watchlist_source_id || position.watchlist_source_id || 'MANUAL',
    managementPolicyVersion:
      frozen.management_policy_version || position.management_policy_version || 'unknown',
  }
}

export default function Positions() {
  const [sorting, setSorting] = useState<any>([{ id: 'pnl_unrealized', desc: true }])
  const [globalFilter, setGlobalFilter] = useState('')
  const [expanded, setExpanded] = useState<string | null>(null)

  const q = useQuery({
    queryKey: ['positions', 'open'],
    queryFn: () => fetchOpenPositions(),
    staleTime: 10000,
  }) as { data?: Position[]; isRefetching?: boolean; refetch?: () => Promise<any> }

  const positions = useMemo(() => (Array.isArray(q.data) ? q.data : []), [q.data])

  const columns = useMemo(
    () => [
      columnHelper.accessor('symbol', {
        header: 'VECTOR (SYM)',
        cell: (info) => (
          <div className="flex items-center gap-2">
            <div
              className={clsx(
                'w-1.5 h-1.5 rounded-full shadow-[0_0_5px_currentColor]',
                info.row.original.asset_class === 'crypto'
                  ? 'text-[#5865F2] bg-[#5865F2]'
                  : 'text-system-online bg-system-online',
              )}
            />
            <span className="font-bold tracking-wider text-white">{info.getValue() || 'UNKNOWN'}</span>
          </div>
        ),
      }),
      columnHelper.accessor('state', {
        header: 'STATUS',
        cell: (info) => <StatusBadge status={info.getValue() || 'unknown'} />,
      }),
      columnHelper.accessor('entry_time', {
        header: 'ACQUIRED_AT',
        cell: (info) => {
          const val = info.getValue()
          return val ? (
            <div className="flex flex-col">
              <span className="text-gray-300 text-xs">{formatET(val)}</span>
              <span className="text-[10px] text-gray-500 font-mono">{relativeTime(val)}</span>
            </div>
          ) : (
            <span className="text-gray-500">—</span>
          )
        },
      }),
      columnHelper.accessor('entry_price', {
        header: 'ENTRY_Px',
        cell: (info) => <span className="text-gray-400 font-mono">{formatCurrency(info.getValue())}</span>,
      }),
      columnHelper.accessor('current_price', {
        header: 'MARK_Px',
        cell: (info) => <span className="text-white font-medium font-mono">{formatCurrency(info.getValue())}</span>,
      }),
      columnHelper.accessor('pnl_unrealized', {
        header: 'LIVE_DELTA',
        cell: (info) => {
          const val = (info.getValue() as number) ?? 0
          return (
            <span
              className={clsx(
                'font-bold font-mono transition-colors duration-300',
                val > 0
                  ? 'text-system-online drop-shadow-[0_0_8px_rgba(16,185,129,0.3)]'
                  : val < 0
                    ? 'text-system-offline drop-shadow-[0_0_8px_rgba(239,68,68,0.3)]'
                    : 'text-gray-400',
              )}
            >
              {val > 0 ? '▲' : val < 0 ? '▼' : '▬'} {formatPnL(val)}
            </span>
          )
        },
      }),
      columnHelper.display({
        id: 'actions',
        header: 'MGMT',
        cell: (info) => {
          const isExpanded = expanded === info.row.original.id
          return (
            <div className="flex justify-center">
              {isExpanded ? (
                <ChevronDown size={16} className="text-brand" />
              ) : (
                <ChevronRight
                  size={16}
                  className="text-gray-600 group-hover:text-brand transition-colors"
                />
              )}
            </div>
          )
        },
      }),
    ],
    [expanded],
  )

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
  const openCount = positions.filter((p) => p.state === 'OPEN').length

  return (
    <div className="space-y-6 max-w-[1600px] mx-auto pb-10 h-full flex flex-col">
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 border-b border-surface-border pb-4 shrink-0">
        <div>
          <h1 className="text-3xl font-bold text-white tracking-tight flex items-center gap-3">
            <TrendingUp className="text-brand" />
            Active Vectors
          </h1>

          <div className="flex items-center gap-3 mt-2 mono text-xs text-gray-500">
            <span>
              TOTAL_EXPOSURE: <span className="text-white">{positions.length}</span>
            </span>
            <span>|</span>
            <span>
              OPEN_OPS: <span className="text-white">{openCount}</span>
            </span>
            <span>|</span>
            <span>
              AGG_DELTA:
              <span className={clsx('ml-1 font-bold', totalPnL >= 0 ? 'text-system-online' : 'text-system-offline')}>
                {formatPnL(totalPnL)}
              </span>
            </span>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="relative group">
            <Search
              size={14}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 group-focus-within:text-brand transition-colors"
            />
            <input
              type="text"
              value={globalFilter ?? ''}
              onChange={(e) => setGlobalFilter(e.target.value)}
              placeholder="Scan Vectors..."
              className="bg-[#12141f] border border-surface-border rounded-lg py-1.5 pl-9 pr-4 text-white font-mono text-sm focus:outline-none focus:border-brand/50 focus:ring-1 focus:ring-brand/50 w-64 transition-all"
            />
          </div>

          <button onClick={() => q.refetch?.()} className="btn-ghost flex items-center gap-2 px-3">
            <RefreshCw size={14} className={(q.isRefetching ?? false) ? 'animate-spin text-brand' : ''} />
          </button>
        </div>
      </div>

      <div className="card p-0 flex-1 flex flex-col overflow-hidden border border-surface-border bg-surface-card/40 backdrop-blur-sm relative z-10 shadow-card-inset">
        <div className="overflow-auto flex-1 scrollbar-thin">
          <table className="w-full text-left border-collapse">
            <thead className="sticky top-0 z-20 bg-[#0b0c13] border-b border-surface-border">
              {table.getHeaderGroups().map((headerGroup) => (
                <tr key={headerGroup.id}>
                  {headerGroup.headers.map((header) => (
                    <th
                      key={header.id}
                      className="py-4 px-5 text-[10px] font-mono font-bold uppercase tracking-widest text-gray-500"
                    >
                      {flexRender(header.column.columnDef.header, header.getContext())}
                    </th>
                  ))}
                </tr>
              ))}
            </thead>

            <tbody>
              {table.getRowModel().rows.map((row) => {
                const isExpanded = expanded === row.original.id
                const milestone = buildMilestoneMetrics(row.original)
                const frozen = buildFrozenPolicyMetrics(row.original)
                const hoursHeldColor = holdColorClass(row.original.time_risk_state, row.original.hold_ratio)
                const targetDrivenExit = milestone.targetDriven

                const tradeStateMetrics: DisplayMetric[] = [
                  {
                    label: 'Quantity',
                    value: formatQuantity(row.original.quantity),
                    mono: true,
                    color: 'text-white',
                  },
                  {
                    label: 'Current Price',
                    value: formatCurrency(row.original.current_price),
                    mono: true,
                    color: 'text-white',
                  },
                  {
                    label: 'Stop Loss',
                    value: formatCurrency(row.original.current_stop ?? row.original.initial_stop),
                    mono: true,
                    color: 'text-system-offline',
                  },
                  {
                    label: 'Trailing Stop',
                    value: milestone.trailActive && milestone.trailingStopValue != null
                      ? formatCurrency(milestone.trailingStopValue)
                      : 'Inactive',
                    mono: true,
                    color: milestone.trailActive ? 'text-system-online' : 'text-gray-500',
                  },
                  {
                    label: 'Hours Held',
                    value: formatHeldHours(row.original.hours_held),
                    color: hoursHeldColor,
                  },
                  {
                    label: 'Max Hold Window',
                    value: formatHoldHours(frozen.maxHoldHours),
                    color: 'text-gray-300',
                  },
                ]

                const protectionMetrics: DisplayMetric[] = [
                  {
                    label: 'Initial Stop',
                    value: formatCurrency(frozen.initialStop),
                    mono: true,
                    color: 'text-gray-300',
                  },
                  {
                    label: 'Current Protection',
                    value: formatCurrency(milestone.protectedFloor),
                    mono: true,
                    color: 'text-white',
                  },
                  {
                    label: 'Trail Active',
                    value: yesNo(milestone.trailActive),
                    color: milestone.trailActive ? 'text-system-online' : 'text-gray-400',
                  },
                  {
                    label: 'TP1 Hit',
                    value: targetDrivenExit ? yesNo(milestone.tp1Hit) : 'N/A',
                    color: targetDrivenExit
                      ? milestone.tp1Hit
                        ? 'text-system-online'
                        : 'text-gray-400'
                      : 'text-gray-500',
                  },
                  {
                    label: 'Promoted',
                    value: targetDrivenExit ? yesNo(milestone.promoted) : 'N/A',
                    color: targetDrivenExit
                      ? milestone.promoted
                        ? 'text-system-online'
                        : 'text-gray-400'
                      : 'text-gray-500',
                  },
                ]

                const strategyMetrics: DisplayMetric[] = [
                  {
                    label: 'Entry',
                    value: toTitleCase(String(frozen.entryStrategy)),
                    color: 'text-white',
                  },
                  {
                    label: 'Exit',
                    value: toTitleCase(String(frozen.exitStrategy)),
                    color: 'text-white',
                  },
                  {
                    label: 'Entry Regime',
                    value: toTitleCase(String(frozen.regimeAtEntry)),
                    color: 'text-gray-300',
                  },
                  {
                    label: 'Market Regime',
                    value: toTitleCase(String(frozen.marketRegime)),
                    color: 'text-gray-300',
                  },
                ]

                const targetMetrics: DisplayMetric[] = [
                  {
                    label: 'TP1',
                    value: formatTargetValue(frozen.profitTarget1, targetDrivenExit),
                    mono: true,
                    color: targetDrivenExit ? 'text-system-online' : 'text-gray-500',
                  },
                  {
                    label: 'TP2',
                    value: formatTargetValue(frozen.profitTarget2, targetDrivenExit),
                    mono: true,
                    color: targetDrivenExit ? 'text-system-online' : 'text-gray-500',
                  },
                  {
                    label: 'Hard Max Hold',
                    value: yesNo(frozen.hardMaxHold),
                    color: frozen.hardMaxHold === true ? 'text-white' : 'text-gray-400',
                  },
                  {
                    label: 'Realized PnL',
                    value: formatPnL(row.original.pnl_realized),
                    mono: true,
                    color:
                      (row.original.pnl_realized ?? 0) >= 0
                        ? 'text-system-online'
                        : 'text-system-offline',
                  },
                ]

                const frozenPolicyMetrics: DisplayMetric[] = [
                  {
                    label: 'Policy Version',
                    value: String(frozen.managementPolicyVersion),
                    color: 'text-white',
                  },
                  {
                    label: 'Exit Template',
                    value: toTitleCase(String(frozen.exitStrategy)),
                    color: 'text-white',
                  },
                  {
                    label: 'Max Hold',
                    value: formatHoldHours(frozen.maxHoldHours),
                    color: 'text-gray-300',
                  },
                  {
                    label: 'Regime Lock',
                    value: toTitleCase(String(frozen.regimeAtEntry)),
                    color: 'text-gray-300',
                  },
                  {
                    label: 'Source',
                    value: String(frozen.watchlistSourceId),
                    color: 'text-brand',
                    mono: true,
                  },
                ]

                const milestoneStatusMetrics: DisplayMetric[] = [
                  {
                    label: 'TP1 Status',
                    value: formatTpStatus(milestone.tp1Hit, targetDrivenExit),
                    color: targetDrivenExit
                      ? milestone.tp1Hit
                        ? 'text-system-online'
                        : 'text-gray-400'
                      : 'text-gray-500',
                  },
                  {
                    label: 'Protection Mode',
                    value: milestone.protectionMode,
                    color: 'text-white',
                  },
                  {
                    label: 'Protected Floor',
                    value: formatCurrency(milestone.protectedFloor),
                    mono: true,
                    color: 'text-white',
                  },
                  {
                    label: 'TP1 Price',
                    value: formatTargetValue(milestone.tp1Price, targetDrivenExit),
                    mono: true,
                    color: targetDrivenExit ? 'text-gray-300' : 'text-gray-500',
                  },
                  {
                    label: 'Trailing Stop',
                    value:
                      milestone.trailActive && milestone.trailingStopValue != null
                        ? formatCurrency(milestone.trailingStopValue)
                        : 'Inactive',
                    mono: true,
                    color: milestone.trailActive ? 'text-system-online' : 'text-gray-500',
                  },
                ]

                return (
                  <React.Fragment key={row.id}>
                    <tr
                      className={clsx(
                        'border-b border-surface-border/30 hover:bg-white/[0.02] transition-colors cursor-pointer group',
                        isExpanded ? 'bg-brand/5' : '',
                      )}
                      onClick={() => setExpanded(isExpanded ? null : row.original.id)}
                    >
                      {row.getVisibleCells().map((cell) => (
                        <td key={cell.id} className="py-3 px-5 whitespace-nowrap">
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </td>
                      ))}
                    </tr>

                    {isExpanded && (
                      <tr className="bg-[#0b0c13]/80 animate-in fade-in duration-200">
                        <td colSpan={7} className="px-8 py-6 border-b border-surface-border/50">
                          <div className="grid grid-cols-1 xl:grid-cols-2 gap-8">
                            <div className="space-y-6">
                              <SectionCard title="Trade State" icon={<Activity size={12} />}>
                                <MetricGrid metrics={tradeStateMetrics} />
                              </SectionCard>

                              <SectionCard title="Protection Progress" icon={<Shield size={12} />}>
                                <MetricGrid metrics={protectionMetrics} />
                              </SectionCard>

                              <SectionCard title="Strategy Snapshot" icon={<Zap size={12} />}>
                                <MetricGrid metrics={strategyMetrics} />
                              </SectionCard>
                            </div>

                            <div className="space-y-6">
                              <SectionCard title="Targets & Performance" icon={<Target size={12} />}>
                                <MetricGrid metrics={targetMetrics} />
                              </SectionCard>

                              <SectionCard title="Frozen Management Policy" icon={<Info size={12} />}>
                                <MetricGrid metrics={frozenPolicyMetrics} />
                              </SectionCard>

                              <SectionCard title="Milestone Status" icon={<Wallet size={12} />}>
                                <MetricGrid metrics={milestoneStatusMetrics} />
                              </SectionCard>
                            </div>
                          </div>

                          <div className="mt-6 pt-4 border-t border-surface-border/30 grid grid-cols-1 md:grid-cols-3 gap-4 text-[10px] font-mono uppercase tracking-widest text-gray-500">
                            <div>
                              Algo Exit:
                              <span className="text-gray-300 ml-1">
                                {toTitleCase(row.original.exit_strategy || 'ACTIVE_MONITORING')}
                              </span>
                            </div>
                            <div>
                              Fees Paid:
                              <span className="text-system-offline ml-1">{formatCurrency(row.original.fees_paid)}</span>
                            </div>
                            <div>
                              Source ID:
                              <span className="text-brand ml-1 break-all">{row.original.watchlist_source_id || 'MANUAL'}</span>
                            </div>
                          </div>

                          {hasRiskControls(row.original.risk_controls) && (
                            <div className="mt-6 pt-4 border-t border-surface-border/30 space-y-3">
                              <div className="text-[10px] font-mono uppercase tracking-widest text-gray-500">
                                Risk Controls
                              </div>

                              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-[12px]">
                                <div className="space-y-1">
                                  <div className="text-[9px] text-gray-500 font-mono uppercase tracking-tighter">
                                    Regime
                                  </div>
                                  <div className="text-sm font-bold text-gray-300">
                                    {row.original.risk_controls?.regime_state || '—'}
                                  </div>
                                </div>

                                <div className="space-y-1">
                                  <div className="text-[9px] text-gray-500 font-mono uppercase tracking-tighter">
                                    Maturity
                                  </div>
                                  <div className="text-sm font-bold text-gray-300">
                                    {row.original.risk_controls?.maturity_state || '—'}
                                  </div>
                                </div>

                                <div className="space-y-1">
                                  <div className="text-[9px] text-gray-500 font-mono uppercase tracking-tighter">
                                    Volatility %
                                  </div>
                                  <div className="text-sm font-bold text-gray-300">
                                    {formatPercentage(row.original.risk_controls?.volatility_pct)}
                                  </div>
                                </div>

                                <div className="space-y-1 md:col-span-2">
                                  <div className="text-[9px] text-gray-500 font-mono uppercase tracking-tighter">
                                    Risk Multipliers
                                  </div>

                                  {row.original.risk_controls?.risk_multipliers &&
                                  Object.keys(row.original.risk_controls.risk_multipliers).length > 0 ? (
                                    <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-[11px] font-mono text-gray-300">
                                      {Object.keys(
                                        row.original.risk_controls.risk_multipliers as Record<string, number | null>,
                                      ).map((key) => {
                                        const multiplier = (
                                          row.original.risk_controls!.risk_multipliers as Record<string, number | null>
                                        )[key]

                                        return (
                                          <div key={key} className="flex items-center gap-2">
                                            <span className="text-gray-500">{formatRiskMultiplierLabel(key)}:</span>
                                            <span>{multiplier ?? '—'}</span>
                                          </div>
                                        )
                                      })}
                                    </div>
                                  ) : (
                                    <div className="text-sm font-bold text-gray-500">—</div>
                                  )}
                                </div>
                              </div>
                            </div>
                          )}
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

function SectionCard({
  title,
  icon,
  children,
}: {
  title: string
  icon?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <div className="rounded-xl border border-surface-border/40 bg-white/[0.02] p-4">
      <div className="text-[10px] text-gray-500 font-mono uppercase tracking-widest mb-4 flex items-center gap-2">
        {icon}
        {title}
      </div>
      {children}
    </div>
  )
}

function MetricGrid({ metrics }: { metrics: DisplayMetric[] }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-4">
      {metrics.map((metric) => (
        <SubMetric
          key={metric.label}
          label={metric.label}
          value={metric.value}
          color={metric.color}
          mono={metric.mono}
        />
      ))}
    </div>
  )
}

function SubMetric({
  label,
  value,
  color = 'text-gray-300',
  mono = false,
}: {
  label: string
  value: React.ReactNode | number | string | null | undefined
  color?: string
  mono?: boolean
}) {
  return (
    <div className="space-y-1 min-w-0">
      <div className="text-[9px] text-gray-500 font-mono uppercase tracking-tighter">
        {label}
      </div>
      <div className={clsx('text-sm font-bold break-words', color, mono && 'font-mono')}>
        {value ?? '—'}
      </div>
    </div>
  )
}