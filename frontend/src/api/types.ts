export interface MarketStatusResponse {
  status: 'open' | 'pre_market' | 'eod' | 'closed'
  label: string
  is_trading_day: boolean
}

export interface PositionRecord {
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
  profit_target_1?: number | null
  profit_target_2?: number | null
  initial_stop?: number | null
  current_stop?: number | null
  entry_strategy?: string | null
  exit_strategy?: string | null
  pnl_realized?: number | null
  fees_paid?: number | null
  regime_at_entry?: string | null

  // Management truth
  management_policy_version?: string | null
  milestone_state?: Record<string, any> | null
  frozen_policy?: Record<string, any> | null
}

export interface MonitoringCandidate {
  symbol: string
  asset_class: string
  state: string
  added_at: string | null
  watchlist_source_id: string | null
  top_strategy: string | null
  top_confidence: number | null
  top_entry: number | null

  // Diagnostics
  blocked_reason?: string | null
  has_open_position?: boolean
  cooldown_active?: boolean
  regime_allowed?: boolean | null
  evaluation_error?: string | null
  top_notes?: string | null
  position_or_order_status?: string | null
}

export interface WatchlistItem {
  symbol: string
  asset_class: 'crypto' | 'stock'
  source_id?: string | null
  notes?: string | null
}

export interface LedgerAccount {
  id: string
  asset_class: string
  cash_balance: number
  fees_total: number
  realized_pnl: number
  unrealized_pnl: number
  last_reconciled_at: string | null
  updated_at: string | null
}

export interface LedgerEntry {
  id: string
  asset_class: string
  entry_type: string
  symbol?: string | null
  amount: number
  balance_after: number
  notes?: string | null
  created_at?: string | null
}

export interface Trade {
  id: string
  symbol: string
  asset_class: 'crypto' | 'stock'
  entry_price?: number | null
  exit_price?: number | null
  quantity?: number | null
  entry_time?: string | null
  exit_time?: string | null
  exit_reason?: string | null
  entry_strategy?: string | null
  exit_strategy?: string | null
  pnl_realized?: number | null
  fees_paid?: number | null
  regime_at_entry?: string | null
}

export interface TradeSummary {
  total_trades: number
  winners: number
  losers: number
  win_rate: number
  total_pnl: number
  avg_pnl: number
}

export interface AuditEvent {
  id: string
  event_type: string
  asset_class?: 'crypto' | 'stock' | null
  symbol?: string | null
  position_id?: string | null
  source: string
  event_data?: Record<string, unknown> | null
  message?: string | null
  created_at?: string | null
}

export interface EventTypesResponse {
  event_types: string[]
}

export interface RuntimeState {
  market_open: boolean
  halted?: boolean
  [key: string]: unknown
}

export type ApiListResponse<T> = T[]

export default {} as const
