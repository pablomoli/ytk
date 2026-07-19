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
  // Chroma ids come in two schemes (ingest pipeline and vault reindexer); both
  // end with the note's file stem, and stems are globally unique in the vault.
  const matched = new Map<string, LibraryItem>()
  for (const id of evidenceIds) {
    for (const it of items) {
      if (id.endsWith(it.stem)) {
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
