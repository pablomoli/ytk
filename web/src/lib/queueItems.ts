import type { QueueItem } from '../api/queue'
import { canonicalSource } from '../components/icons'

export function filterAndSortQueue(items: QueueItem[], source?: string): QueueItem[] {
  // Newest-first for every source. `shared_at` is date-only, so a same-day
  // burst (e.g. several iMessage sessions) all tie; the queue arrives in
  // insertion order (oldest-first), so we break ties by original index
  // descending — the later-inserted item is the newer one. Without this the
  // grid renders same-day items backwards (oldest-first, "right to left").
  return items
    .map((item, i) => ({ item, i }))
    .filter(({ item }) => !source || canonicalSource(item.source) === source)
    .sort((a, b) => {
      const byDate = (b.item.shared_at ?? '').localeCompare(a.item.shared_at ?? '')
      return byDate !== 0 ? byDate : b.i - a.i
    })
    .map(({ item }) => item)
}
