import { useState } from 'react'
import type { MouseEvent } from 'react'
import type { QueueItem } from '../api/queue'
import { sourceIcon } from './icons'

type ImageStage = 'cover' | 'preview' | 'fallback'
type CardState = 'queued' | 'ingesting'

function cardClassName(selected?: boolean, state?: CardState): string {
  let cls = 'card'
  if (selected) cls += ' selected'
  if (state) cls += ` ${state}`
  return cls
}

export function Card({
  item,
  onOpen,
  selected,
  state,
}: {
  item: QueueItem
  onOpen: (i: QueueItem) => void
  selected?: boolean
  state?: CardState
}) {
  const [stage, setStage] = useState<ImageStage>('cover')

  const handleClick = (e: MouseEvent<HTMLDivElement>) => {
    if ((e.target as HTMLElement).closest('a')) return
    onOpen(item)
  }

  const handleImageError = () => {
    if (stage === 'cover') {
      setStage(item.preview_url ? 'preview' : 'fallback')
    } else if (stage === 'preview') {
      setStage('fallback')
    }
  }

  if (item.source === 'imessage') {
    return (
      <div className={cardClassName(selected, state)} onClick={handleClick}>
        <div className="textcard">
          <p>{item.text}</p>
          <span>{item.author}</span>
        </div>
      </div>
    )
  }

  return (
    <div className={cardClassName(selected, state)} onClick={handleClick}>
      {stage === 'fallback' ? (
        <div className="noimg">{item.source}</div>
      ) : (
        <img
          src={stage === 'preview' ? item.preview_url : `/api/cover?u=${encodeURIComponent(item.url)}`}
          loading="lazy"
          alt=""
          onError={handleImageError}
        />
      )}
      {state === 'ingesting' ? <div className="spinner" /> : null}
      <div className="meta">
        <div className="title">{item.text || item.author || item.url}</div>
        <div className="sub">
          {sourceIcon(item.source)}
          <span data-testid="card-source">{item.source}</span>
        </div>
      </div>
    </div>
  )
}
