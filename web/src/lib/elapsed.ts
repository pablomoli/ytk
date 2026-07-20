/* Format an elapsed duration as m:ss. `startedAt` is an epoch-seconds value
   that may carry a fractional part (the backend stamps it with time.time()),
   so the difference is floored to whole seconds — otherwise the fraction
   leaks into the display as "0:12.166681...". */
export function formatElapsed(nowSec: number, startedAt?: number | null): string {
  if (!startedAt) return ''
  const secs = Math.max(0, Math.floor(nowSec - startedAt))
  return `${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, '0')}`
}
