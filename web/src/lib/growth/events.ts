export type LibraryItem = {
  stem: string
  title: string
  url: string | null
  tags: string[]
  date: string | null
  added: string
  thumbnail: string | null
  source: string
}

export function joinEvidence(evidenceIds: string[], items: LibraryItem[]): LibraryItem[] {
  // Evidence ids come in three schemes: note ids from the ingest pipeline and
  // the vault reindexer (both end with the note's globally-unique file stem),
  // and bare YouTube video ids, which only appear inside the note's url.
  const matched = new Map<string, LibraryItem>()
  for (const id of evidenceIds) {
    for (const it of items) {
      if (id.endsWith(it.stem) || (id.length >= 8 && it.url?.includes(id))) {
        matched.set(it.stem, it)
        break
      }
    }
  }
  return [...matched.values()].sort((a, b) => (a.date ?? a.added).localeCompare(b.date ?? b.added))
}

export function tagCountsOf(items: LibraryItem[]): Record<string, number> {
  const counts: Record<string, number> = {}
  for (const it of items) {
    for (const t of it.tags) counts[t] = (counts[t] ?? 0) + 1
  }
  return counts
}

export function dominantTags(items: LibraryItem[], n = 6): string[] {
  return Object.entries(tagCountsOf(items))
    .sort((a, b) => b[1] - a[1])
    .slice(0, n)
    .map(([t]) => t)
}

export function classifyEvent(noteTags: string[], dominant: string[]): 'related' | 'novel' {
  return noteTags.some((t) => dominant.includes(t)) ? 'related' : 'novel'
}
