import clsx from 'clsx'

type StatusBadgeProps = {
  status: string | null | undefined
  showRaw?: boolean
}

type Mapped = {
  semantic: string
  label: string
  cls: string
  raw: string
}

function mapStatus(rawIn: string | null | undefined): Mapped {
  const raw = String(rawIn ?? 'unknown').trim()
  const u = raw.toUpperCase()

  if (['SKIPPED', 'POSITION_SIZER_RETURNED_ZERO'].includes(u)) {
    return { semantic: 'skipped', label: 'Skipped', cls: 'bg-sky-600/8 text-sky-300 border border-sky-600/30', raw }
  }

  // Friendly operator labels and consistent semantic buckets
  if (['ONLINE', 'RUNNING', 'ACTIVE', 'OPEN', 'FILLED'].includes(u)) {
    return { semantic: 'online', label: 'Online', cls: 'bg-emerald-500/10 text-emerald-300 border border-emerald-500/30', raw }
  }

  if (['PENDING', 'SUBMITTED', 'MANAGED'].includes(u) || u === 'IDLE') {
    // Pending states use amber to signal attention but not error
    return { semantic: 'pending', label: 'Pending', cls: 'bg-amber-600/8 text-amber-300 border border-amber-600/30', raw }
  }

  if (u === 'PAUSED') {
    return { semantic: 'paused', label: 'Paused', cls: 'bg-slate-700/10 text-slate-300 border border-slate-600/30', raw }
  }

  if (u.includes('PRE') && u.includes('MARKET')) {
    // Pre-market uses a sky/cyan palette to distinguish from amber pending
    return { semantic: 'pre-market', label: 'Pre-Market', cls: 'bg-sky-600/8 text-sky-300 border border-sky-600/30', raw }
  }

  if (u === 'EOD' || u === 'END_OF_DAY') {
    // EOD uses a warmer amber with stronger background to indicate restricted window
    return { semantic: 'eod', label: 'EOD', cls: 'bg-amber-700/10 text-amber-300 border border-amber-700/30', raw }
  }

  if (['INACTIVE', 'CLOSED', 'STOPPED', 'OFFLINE', 'UNKNOWN'].includes(u)) {
    return { semantic: 'offline', label: 'Offline', cls: 'bg-gray-700/6 text-gray-400 border border-gray-600/30', raw }
  }

  if (['CANCELLED', 'REJECTED', 'ERROR', 'FAILED'].includes(u)) {
    return { semantic: 'error', label: 'Error', cls: 'bg-red-600/8 text-red-400 border border-red-600/30', raw }
  }

  // Fallback: return a neutral mapping but preserve raw text
  return { semantic: 'unknown', label: raw || 'Unknown', cls: 'bg-gray-700/6 text-gray-400 border border-gray-600/30', raw }
}


export default function StatusBadge({ status, showRaw }: StatusBadgeProps) {
  const mapped = mapStatus(status)

  return (
    <span
      className={clsx('inline-flex items-center gap-2 px-2 py-0.5 rounded text-xs font-mono uppercase', mapped.cls)}
      title={`Backend: ${mapped.raw}`}
      aria-label={`Status ${mapped.label}`}
    >
      <span className="font-medium">{mapped.label}</span>
      {showRaw && mapped.raw && mapped.raw.toUpperCase() !== mapped.label.toUpperCase() && (
        <span className="text-[11px] text-gray-400 ml-1">{`(${mapped.raw})`}</span>
      )}
    </span>
  )
}
