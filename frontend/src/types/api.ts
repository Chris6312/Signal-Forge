export interface PositionRiskControls {
  risk_multipliers?: Record<string, number | null> | null
  volatility_pct?: number | null
  maturity_state?: string | null
  regime_state?: string | null
}
