export type NoteFrontmatter = {
  title?: string
  url?: string
  uploader?: string
  date?: string
  duration?: string
  tags: string[]
  images: string[]
}

export type NoteSectionKind = 'thesis' | 'commentary' | 'insights' | 'concepts' | 'moments' | 'transcript' | 'generic'

export type NoteSection = {
  heading: string
  kind: NoteSectionKind
  body: string
}

export type ParsedNote = {
  frontmatter: NoteFrontmatter
  sections: NoteSection[]
  lead?: string
}

const KIND_BY_HEADING: Record<string, NoteSectionKind> = {
  thesis: 'thesis',
  commentary: 'commentary',
  insights: 'insights',
  'key concepts': 'concepts',
  concepts: 'concepts',
  'key moments': 'moments',
  moments: 'moments',
  transcript: 'transcript',
}

function kindForHeading(heading: string): NoteSectionKind {
  return KIND_BY_HEADING[heading.trim().toLowerCase()] ?? 'generic'
}

function stripQuotes(value: string): string {
  const trimmed = value.trim()
  if (trimmed.length >= 2) {
    const first = trimmed[0]
    const last = trimmed[trimmed.length - 1]
    if ((first === '"' && last === '"') || (first === "'" && last === "'")) {
      return trimmed.slice(1, -1)
    }
  }
  return trimmed
}

function parseInlineList(value: string): string[] {
  const inner = value.trim().replace(/^\[/, '').replace(/\]$/, '')
  if (!inner.trim()) return []
  return inner.split(',').map((item) => stripQuotes(item)).filter(Boolean)
}

/** Collects a YAML block list (`  - item` lines following a bare `key:`).
    Returns the parsed items and the index of the first line after the list. */
function collectBlockList(lines: string[], startIndex: number): { items: string[]; nextIndex: number } {
  const collected: string[] = []
  let j = startIndex
  while (j < lines.length && /^\s*-\s*/.test(lines[j])) {
    collected.push(stripQuotes(lines[j].replace(/^\s*-\s*/, '')))
    j++
  }
  return { items: collected.filter(Boolean), nextIndex: j }
}

function splitFrontmatter(raw: string): { fm: string | null; rest: string } {
  if (!raw.startsWith('---')) return { fm: null, rest: raw }
  const lines = raw.split('\n')
  if (lines[0].trim() !== '---') return { fm: null, rest: raw }
  let end = -1
  for (let i = 1; i < lines.length; i++) {
    if (lines[i].trim() === '---') { end = i; break }
  }
  if (end === -1) return { fm: null, rest: raw }
  const fm = lines.slice(1, end).join('\n')
  const rest = lines.slice(end + 1).join('\n')
  return { fm, rest }
}

function parseFrontmatter(fm: string | null): NoteFrontmatter {
  const result: NoteFrontmatter = { tags: [], images: [] }
  if (!fm) return result
  const lines = fm.split('\n')
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    const match = line.match(/^([A-Za-z_][\w-]*)\s*:\s*(.*)$/)
    if (!match) continue
    const key = match[1].trim().toLowerCase()
    const value = match[2]

    if (key === 'tags' || key === 'image_paths') {
      const trimmedValue = value.trim()
      let items: string[] = []
      if (trimmedValue.startsWith('[')) {
        items = parseInlineList(trimmedValue)
      } else if (!trimmedValue) {
        const { items: collected, nextIndex } = collectBlockList(lines, i + 1)
        items = collected
        i = nextIndex - 1
      }
      if (key === 'tags') result.tags = items
      else result.images = items
      continue
    }

    const scalarValue = stripQuotes(value)
    if (key === 'title') result.title = scalarValue
    else if (key === 'url') result.url = scalarValue
    else if (key === 'uploader') result.uploader = scalarValue
    else if (key === 'date') result.date = scalarValue
    else if (key === 'duration') result.duration = scalarValue
  }
  return result
}

/** Drops Obsidian embeds (`![[...]]`) so the literal syntax never leaks into
    rendered text — whole embed-only lines are dropped outright, any embed
    remaining inline within other text is stripped in place. */
function stripEmbeds(text: string): string {
  const withoutEmbedLines = text
    .split('\n')
    .filter((line) => !/^\s*!\[\[.*\]\]\s*$/.test(line))
    .join('\n')
  return withoutEmbedLines
    .replace(/!\[\[[^\]]*\]\]/g, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

export function parseNote(raw: string): ParsedNote {
  const { fm, rest } = splitFrontmatter(raw)
  const frontmatter = parseFrontmatter(fm)

  const body = fm !== null ? rest.replace(/^\n+/, '') : rest

  const headingRe = /^## (.*)$/gm
  const matches = [...body.matchAll(headingRe)]

  if (matches.length === 0) {
    return { frontmatter, sections: [], lead: stripEmbeds(body) }
  }

  const leadRaw = body.slice(0, matches[0].index ?? 0)
  const lead = stripEmbeds(leadRaw)

  const sections: NoteSection[] = matches.map((m, idx) => {
    const heading = m[1].trim()
    const start = (m.index ?? 0) + m[0].length
    const end = idx + 1 < matches.length ? matches[idx + 1].index! : body.length
    const sectionBody = stripEmbeds(body.slice(start, end))
    return { heading, kind: kindForHeading(heading), body: sectionBody }
  })

  return { frontmatter, sections, lead }
}
