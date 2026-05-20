/** Colombia is permanently UTC-5 (no DST). */
const COL_TZ = 'America/Bogota';

/** Returns today's date in Colombia timezone as YYYY-MM-DD. */
export function todayCol(): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: COL_TZ }).format(new Date());
}

/** Returns yesterday's date in Colombia timezone as YYYY-MM-DD. */
export function yesterdayCol(): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: COL_TZ }).format(new Date(Date.now() - 86_400_000));
}

/**
 * Converts a UTC ISO string (from backend) to a datetime-local string
 * showing the time in Colombia timezone (for <input type="datetime-local">).
 * e.g. "2026-05-15T15:00:00Z" → "2026-05-15T10:00"
 */
export function utcToColLocal(utcIso: string): string {
  const date = new Date(utcIso);
  // sv-SE locale gives "YYYY-MM-DD HH:mm" format → easy to convert to datetime-local
  return new Intl.DateTimeFormat('sv-SE', {
    timeZone: COL_TZ,
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  }).format(date).replace(' ', 'T');
}

/**
 * Converts a datetime-local string (treated as Colombia time) to a UTC ISO string.
 * Colombia is always UTC-5, so we add 5 hours.
 * e.g. "2026-05-15T10:00" → "2026-05-15T15:00:00.000Z"
 */
export function colLocalToUtc(localStr: string): string {
  const [datePart, timePart] = localStr.split('T');
  const [year, month, day] = datePart.split('-').map(Number);
  const [hour, minute] = (timePart ?? '00:00').split(':').map(Number);
  return new Date(Date.UTC(year, month - 1, day, hour + 5, minute)).toISOString();
}
