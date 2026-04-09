import clsx from 'clsx'

type Status = string

const statusMap: Record<string, string> = {
  ACTIVE: 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30',
  OPEN: 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30',
  FILLED: 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30',
  running: 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30',
  online: 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30',

  MANAGED: 'bg-amber-500/20 text-amber-400 border border-amber-500/30',
  PENDING: 'bg-amber-500/20 text-amber-400 border border-amber-500/30',
  SUBMITTED: 'bg-amber-500/20 text-amber-400 border border-amber-500/30',
  idle: 'bg-amber-500/20 text-amber-400 border border-amber-500/30',

  paused: 'bg-slate-500/20 text-slate-400 border border-slate-500/30',
  'pre-market': 'bg-sky-500/20 text-sky-400 border border-sky-500/30',
  eod: 'bg-amber-500/20 text-amber-400 border border-amber-500/30',

  INACTIVE: 'bg-gray-500/20 text-gray-400 border border-gray-500/30',
  CLOSED: 'bg-gray-500/20 text-gray-400 border border-gray-500/30',
  stopped: 'bg-gray-500/20 text-gray-400 border border-gray-500/30',
  offline: 'bg-gray-500/20 text-gray-400 border border-gray-500/30',
  unknown: 'bg-gray-500/20 text-gray-400 border border-gray-500/30',

  CANCELLED: 'bg-red-500/20 text-red-400 border border-red-500/30',
  REJECTED: 'bg-red-500/20 text-red-400 border border-red-500/30',
}

export default function StatusBadge({ status }: { status: Status }) {
  const cls = statusMap[status] ?? 'bg-gray-500/20 text-gray-400 border border-gray-500/30'
  return (
    <span className={clsx('badge', cls)}>
      {status}
    </span>
  )
}
