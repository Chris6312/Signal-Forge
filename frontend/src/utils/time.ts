import { formatDistanceToNow } from 'date-fns'

const TZ = 'America/New_York'

// sv-SE locale naturally produces ISO-style "yyyy-MM-dd HH:mm:ss"
const _dateFmt = new Intl.DateTimeFormat('sv-SE', {
  timeZone: TZ,
  year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', second: '2-digit',
  hour12: false,
})

const _tzFmt = new Intl.DateTimeFormat('en-US', {
  timeZone: TZ,
  timeZoneName: 'short',
})

/**
 * Parse a date value, treating naive strings (no Z or UTC offset) as UTC.
 * The backend stores datetimes as timezone-naive UTC, so without this they
 * would be mis-parsed as local time by the browser.
 */
function parseUTC(value: string | Date): Date {
  if (value instanceof Date) return value
  // If the string has no timezone indicator, assume UTC and append Z
  if (!/Z|[+-]\d{2}:?\d{2}$/.test(value)) {
    return new Date(value.includes('T') ? value + 'Z' : value.replace(' ', 'T') + 'Z')
  }
  return new Date(value)
}

/** Format a UTC date string as a literal Eastern Time datetime, e.g. "2026-04-08 09:15:30 EDT" */
export function formatET(value: string | Date | null | undefined): string {
  if (!value) return '—'
  try {
    const d = parseUTC(value)
    const base = _dateFmt.format(d)
    const tzName = _tzFmt.formatToParts(d).find(p => p.type === 'timeZoneName')?.value ?? 'ET'
    return `${base} ${tzName}`
  } catch {
    return '—'
  }
}

/** Human-readable relative time, e.g. "3 minutes ago" — uses same UTC-safe parser. */
export function relativeTime(value: string | Date | null | undefined): string {
  if (!value) return '—'
  try {
    return formatDistanceToNow(parseUTC(value), { addSuffix: true })
  } catch {
    return '—'
  }
}
