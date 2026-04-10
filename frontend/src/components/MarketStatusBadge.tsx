import { useQuery } from '@tanstack/react-query'
import { fetchMarketStatus } from '@/api/endpoints'
import type { MarketStatusResponse } from '@/api/types'
import clsx from 'clsx'

const statusConfig: Record<
  MarketStatusResponse['status'],
  { dot: string; text: string; bg: string; border: string }
> = {
  open: {
    dot:    'bg-emerald-400 animate-pulse',
    text:   'text-emerald-400',
    bg:     'bg-emerald-500/10',
    border: 'border-emerald-500/20',
  },
  pre_market: {
    dot:    'bg-amber-400',
    text:   'text-amber-400',
    bg:     'bg-amber-500/10',
    border: 'border-amber-500/20',
  },
  eod: {
    dot:    'bg-amber-400 animate-pulse',
    text:   'text-amber-400',
    bg:     'bg-amber-500/10',
    border: 'border-amber-500/20',
  },
  closed: {
    dot:    'bg-gray-500',
    text:   'text-gray-500',
    bg:     'bg-gray-500/10',
    border: 'border-gray-500/20',
  },
}

export default function MarketStatusBadge() {
  const q = useQuery({
    queryKey: ['market-status'],
    queryFn: fetchMarketStatus,
    // Re-check every 60 s — status only changes on minute boundaries
    refetchInterval: 60_000,
    staleTime: 30_000,
  })

  const data = q.data as MarketStatusResponse | undefined
  const status = data?.status ?? 'closed'
  const label  = data?.label  ?? 'Market Closed'
  const cfg    = statusConfig[status]

  return (
    <div
      className={clsx(
        'mx-3 mb-1 flex items-center gap-2 rounded-lg border px-3 py-2',
        cfg.bg,
        cfg.border,
      )}
    >
      {/* pulsing / static dot */}
      <span className={clsx('h-2 w-2 rounded-full shrink-0', cfg.dot)} />
      <span className={clsx('text-xs font-medium', cfg.text)}>{label}</span>
    </div>
  )
}
