import React, { Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from '@/components/Layout'

const Dashboard    = React.lazy(() => import('@/pages/Dashboard'))
const Watchlist    = React.lazy(() => import('@/pages/Watchlist'))
const Monitoring   = React.lazy(() => import('@/pages/Monitoring'))
const Positions    = React.lazy(() => import('@/pages/Positions'))
const Ledger       = React.lazy(() => import('@/pages/Ledger'))
const TradeHistory = React.lazy(() => import('@/pages/TradeHistory'))
const AuditTrail   = React.lazy(() => import('@/pages/AuditTrail'))
const RuntimeRisk  = React.lazy(() => import('@/pages/RuntimeRisk'))

function PageLoader() {
  return (
    <div className="flex h-full items-center justify-center p-12">
      <div className="h-6 w-6 animate-spin rounded-full border-2 border-brand border-t-transparent" />
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<PageLoader />}>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<Navigate to="/dashboard" replace />} />
            <Route path="dashboard" element={<Dashboard />} />
            <Route path="watchlist" element={<Watchlist />} />
            <Route path="monitoring" element={<Monitoring />} />
            <Route path="positions" element={<Positions />} />
            <Route path="ledger" element={<Ledger />} />
            <Route path="trades" element={<TradeHistory />} />
            <Route path="audit" element={<AuditTrail />} />
            <Route path="runtime" element={<RuntimeRisk />} />
          </Route>
        </Routes>
      </Suspense>
    </BrowserRouter>
  )
}

