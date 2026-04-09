import api from './client'

export const fetchDashboard = () => api.get('/dashboard').then(r => r.data)
export const fetchHealth = () => api.get('/health', { baseURL: import.meta.env.VITE_API_URL || '' }).then(r => r.data)

export const fetchWatchlist = (params?: Record<string, string>) =>
  api.get('/watchlist', { params }).then(r => r.data)
export const fetchActiveWatchlist = () => api.get('/watchlist/active').then(r => r.data)
export const postWatchlistUpdate = (body: { watchlist: object[]; source_id?: string }) =>
  api.post('/watchlist/update', body).then(r => r.data)

export const fetchMonitoringCandidates = (params?: Record<string, string>) =>
  api.get('/monitoring', { params }).then(r => r.data)
export const evaluateSymbol = (symbol: string, asset_class: string) =>
  api.get(`/monitoring/evaluate/${symbol}`, { params: { asset_class } }).then(r => r.data)

export const fetchPositions = (params?: Record<string, string>) =>
  api.get('/positions', { params }).then(r => r.data)
export const fetchOpenPositions = () => api.get('/positions/open').then(r => r.data)
export const fetchPosition = (id: string) => api.get(`/positions/${id}`).then(r => r.data)
export const fetchPositionOrders = (id: string) => api.get(`/positions/${id}/orders`).then(r => r.data)

export const fetchLedgerAccounts = () => api.get('/ledger/accounts').then(r => r.data)
export const fetchLedgerEntries = (params?: Record<string, string>) =>
  api.get('/ledger/entries', { params }).then(r => r.data)
export const postAdjustment = (body: { asset_class: string; amount: number; notes: string }) =>
  api.post('/ledger/adjust', body).then(r => r.data)

export const fetchTradeHistory = (params?: Record<string, string>) =>
  api.get('/trades', { params }).then(r => r.data)
export const fetchTradeSummary = (params?: Record<string, string>) =>
  api.get('/trades/summary', { params }).then(r => r.data)

export const fetchAuditEvents = (params?: Record<string, string>) =>
  api.get('/audit', { params }).then(r => r.data)
export const fetchEventTypes = () => api.get('/audit/event-types').then(r => r.data)

export const fetchRuntime = () => api.get('/runtime').then(r => r.data)
export const fetchMarketStatus = () => api.get('/runtime/market-status').then(r => r.data)
export const patchRuntime = (body: object, adminToken: string) =>
  api.patch('/runtime', body, { headers: { 'x-admin-token': adminToken } }).then(r => r.data)
export const haltTrading = (adminToken: string) =>
  api.post('/runtime/halt', {}, { headers: { 'x-admin-token': adminToken } }).then(r => r.data)
export const resumeTrading = (adminToken: string) =>
  api.post('/runtime/resume', {}, { headers: { 'x-admin-token': adminToken } }).then(r => r.data)
export const resetPaperData = (
  adminToken: string,
  initialCryptoBalance: number,
  initialStockBalance: number,
) =>
  api.post('/runtime/reset', {}, {
    headers: { 'x-admin-token': adminToken },
    params: {
      initial_crypto_balance: initialCryptoBalance,
      initial_stock_balance:  initialStockBalance,
    },
  }).then(r => r.data)
