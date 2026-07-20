import type { ReactNode } from 'react'

const TOKEN_RE = /\*\*(.+?)\*\*|\[([^\]]+)\]\(([^)]+)\)/g

/** A tiny owned inline-markdown renderer: **bold** and [label](url) only.
    Single-pass tokenizer — these notes never use nested/edge-case markdown. */
export function renderInline(text: string): ReactNode {
  const nodes: ReactNode[] = []
  let lastIndex = 0
  let match: RegExpExecArray | null
  let key = 0

  TOKEN_RE.lastIndex = 0
  while ((match = TOKEN_RE.exec(text))) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index))
    }
    if (match[1] !== undefined) {
      nodes.push(<strong key={key++}>{match[1]}</strong>)
    } else {
      nodes.push(
        <a key={key++} href={match[3]} target="_blank" rel="noreferrer">
          {match[2]}
        </a>,
      )
    }
    lastIndex = match.index + match[0].length
  }
  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex))
  }

  return nodes.length === 1 ? nodes[0] : nodes
}
