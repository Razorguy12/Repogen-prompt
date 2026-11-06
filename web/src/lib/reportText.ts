/** Shared text and time helpers for clinical report views. */

/** "120-180" -> "120–180" for display. Never assumes fixed ranges. */
export function displayRange(wordLimit: string): string {
  return (wordLimit || '').replace(/\s*-\s*/, '–')
}

export const DISPLAY_TZ = 'Asia/Kolkata'

/**
 * Parse an API timestamp as UTC. Older endpoints emit naive ISO strings
 * (no offset) that are UTC by construction; browsers would otherwise read
 * them as local time.
 */
export function parseUtc(iso: string): Date {
  if (!iso) return new Date(NaN)
  const hasZone = /[zZ]$|[+-]\d\d:?\d\d$/.test(iso)
  return new Date(hasZone || iso.length <= 10 ? iso : `${iso}Z`)
}

/** "06 Nov 2026, 5:31 PM IST" in the clinic timezone. */
export function formatDateTime(iso: string, timeZone = DISPLAY_TZ): string {
  const d = parseUtc(iso)
  if (Number.isNaN(d.getTime())) return ''
  const date = new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short', year: 'numeric', timeZone }).format(d)
  const time = new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit', hour12: true, timeZone }).format(d)
  const zone = timeZone === DISPLAY_TZ ? 'IST' : timeZone
  return `${date}, ${time} ${zone}`
}

/** Calendar date ("2026-11-06") -> "06 Nov 2026". Not shifted by timezone. */
export function formatStudyDate(isoDate: string): string {
  if (!isoDate) return ''
  const [y, m, d] = isoDate.slice(0, 10).split('-').map(Number)
  const date = new Date(Date.UTC(y, m - 1, d))
  return new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(date)
}

/** Today's calendar date in the clinic timezone, as YYYY-MM-DD. */
export function todayInClinic(timeZone = DISPLAY_TZ): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone, year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date())
}
