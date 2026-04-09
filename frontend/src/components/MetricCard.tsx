import clsx from 'clsx'
import type { ReactNode } from 'react'

interface MetricCardProps {
  label: string
  value: string | number
  sub?: string
  icon?: ReactNode
  positive?: boolean
  negative?: boolean
  mono?: boolean
}

export default function MetricCard({ label, value, sub, icon, positive, negative, mono }: MetricCardProps) {
  return (
    <div className="card flex flex-col gap-2">
      <div className="flex items-center justify-between text-gray-400 text-xs uppercase tracking-wider">
        <span>{label}</span>
        {icon && <span className="text-gray-500">{icon}</span>}
      </div>
      <div className={clsx(
        'text-2xl font-semibold',
        mono && 'mono',
        positive && 'text-emerald-400',
        negative && 'text-red-400',
        !positive && !negative && 'text-white',
      )}>
        {value}
      </div>
      {sub && <div className="text-xs text-gray-500">{sub}</div>}
    </div>
  )
}
