import { useRef, useState } from 'react'
import type { MouseEvent } from 'react'
import type { FreshNote } from '../api/fresh'
import { useHoverDecode } from '../lib/useHoverDecode'
import { sourceIcon } from './icons'
import { MemoWaveform } from './MemoWaveform'
import { PixelBloom } from './PixelBloom'
import { PixelDissolve } from './PixelDissolve'

export function FreshCard({
  note,
  onOpen,
  onDelete,
}: {
  note: FreshNote
  onOpen: (note: FreshNote, rect?: DOMRect) => void
  onDelete: (note: FreshNote) => void
}) {
  const [imageFailed, setImageFailed] = useState(false)
  const [revealed, setRevealed] = useState(false) // image bytes arrived
  const [reveal, setReveal] = useState(true)      // dissolve still owed
  const isMemo = note.source === 'memo'
  const cardRef = useRef<HTMLElement>(null)
  const decode = useHoverDecode()

  const open = () => onOpen(note, cardRef.current?.getBoundingClientRect())
  const handleClick = (event: MouseEvent<HTMLDivElement>) => {
    if ((event.target as HTMLElement).closest('a, button')) return
    open()
  }
  return (
    <article
      ref={cardRef}
      className="card fresh-card"
      onClick={handleClick}
      data-cursor-target=""
    >
      <PixelBloom />
      <button
        className="delete-note"
        type="button"
        aria-label={`Delete ${note.title}`}
        onClick={() => onDelete(note)}
      >
        ×
      </button>
      {note.has_take ? <span className="take" title="has a take" /> : null}
      {isMemo ? (
        <div className="memocard">
          <div className="memokind">
            {note.kind || 'memo'}{note.date ? ` · ${note.date}` : ''}
          </div>
          <p>{note.preview || note.title}</p>
          {note.audio ? <MemoWaveform audio={note.audio} /> : null}
          <button className="card-open" type="button" onClick={open}>open note</button>
        </div>
      ) : note.thumbnail && !imageFailed ? (
        <div className="thumb-wrap">
          <img
            src={`/vault-media/${note.thumbnail}`}
            loading="lazy"
            alt=""
            onLoad={() => setRevealed(true)}
            onError={() => setImageFailed(true)}
          />
          {!revealed ? null : reveal ? <PixelDissolve seedKey={note.path} cell={22} color="var(--bg2)" onDone={() => setReveal(false)} /> : null}
        </div>
      ) : (
        <div className="noimg">{note.source}</div>
      )}
      {isMemo ? null : (
        <div className="meta">
          <div className="title" onMouseEnter={decode.onMouseEnter}>{note.title}</div>
          {note.tags.length ? <div className="tags">{note.tags.map((tag) => `#${tag}`).join(' ')}</div> : null}
          <div className="sub">
            {sourceIcon(note.source)}
            {note.url ? (
              <a href={note.url} target="_blank" rel="noreferrer">
                open
              </a>
            ) : null}
            <button className="card-open" type="button" onClick={open}>open note</button>
          </div>
        </div>
      )}
    </article>
  )
}
