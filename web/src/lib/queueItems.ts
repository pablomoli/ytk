import type { QueueItem } from '../api/queue'
import { canonicalSource } from '../components/icons'

export function filterAndSortQueue(items: QueueItem[], source?: string): QueueItem[] {
  return items
    .filter((item) => !source || canonicalSource(item.source) === source)
    .toSorted((a, b) => (b.shared_at ?? '').localeCompare(a.shared_at ?? ''))
}
