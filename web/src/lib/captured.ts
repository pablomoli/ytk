/* Queue rows carry shared_at as a plain calendar date ("2026-01-06").

   Formatted in UTC on purpose: parsing a bare date yields UTC midnight, so
   rendering it in the local zone shows the previous day for anyone west of
   Greenwich — a capture date that is silently wrong by one is worse than a
   blunt one. Absolute rather than relative for the same reason a card should
   not need a clock: "6 Jan" means the same thing whenever it is read. */

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function capturedLabel(sharedAt?: string | null): string {
  if (!sharedAt) return "";
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(sharedAt.trim());
  if (!match) return "";
  const [, year, month, day] = match;
  const name = MONTHS[Number(month) - 1];
  if (!name) return "";
  return `${Number(day)} ${name} ${year}`;
}
