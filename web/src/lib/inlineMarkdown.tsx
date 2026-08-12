import type { ReactNode } from "react";

// Bold (**x**) is matched before italic (*x*) so the double-star isn't eaten
// by the single-star branch. Italic uses [^*] to stay inside one run, and
// only *asterisk* italic — not _underscore_ — so snake_case identifiers,
// common in these dev notes, are left untouched.
// The markdown-link branch precedes the bare-URL branch so a [label](url)
// consumes its own URL before the bare-URL alternative can see it.
const TOKEN_RE = /\*\*(.+?)\*\*|\*([^*\n]+)\*|\[([^\]]+)\]\(([^)]+)\)|(https?:\/\/[^\s<>]+)/g;

/** A tiny owned inline-markdown renderer: **bold**, *italic*, [label](url),
    and bare http(s) URLs autolinked verbatim.
    Single-pass tokenizer — these notes never use nested/edge-case markdown. */
export function renderInline(text: string): ReactNode {
  const nodes: ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let key = 0;

  TOKEN_RE.lastIndex = 0;
  while ((match = TOKEN_RE.exec(text))) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }
    if (match[1] !== undefined) {
      nodes.push(<strong key={key++}>{match[1]}</strong>);
    } else if (match[2] !== undefined) {
      nodes.push(<em key={key++}>{match[2]}</em>);
    } else if (match[3] !== undefined) {
      nodes.push(
        <a key={key++} href={match[4]} target="_blank" rel="noreferrer">
          {match[3]}
        </a>,
      );
    } else {
      // sentence punctuation hugging a URL's tail is prose, not address
      const url = match[5].replace(/[.,;:!?)\]'"]+$/, "");
      nodes.push(
        <a key={key++} href={url} target="_blank" rel="noreferrer">
          {url}
        </a>,
      );
      const trailing = match[5].slice(url.length);
      if (trailing) nodes.push(trailing);
    }
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }

  return nodes.length === 1 ? nodes[0] : nodes;
}
