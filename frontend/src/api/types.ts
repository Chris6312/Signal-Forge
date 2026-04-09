export interface MarketStatusResponse {
  status: 'open' | 'pre_market' | 'eod' | 'closed'
  label: string
  is_trading_day: boolean
}
