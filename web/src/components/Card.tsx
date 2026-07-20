import { useState } from 'react'
import type { KeyboardEvent, MouseEvent } from 'react'
import type { QueueItem } from '../api/queue'
import type { ProfileRankPick } from '../api/profileRank'
import { PixelBloom } from './PixelBloom'
import { sourceIcon } from './icons'

type ImageStage = 'cover' | 'preview' | 'fallback'
type CardState = 'queued' | 'ingesting'

function cardClassName(selected?: boolean, state?: CardState, profileMatch?: boolean): string {
  let cls = 'card'
  if (selected) cls += ' selected'
  if (state) cls += ` ${state}`
  if (profileMatch) cls += ' profile-match'
  return cls
}

export function Card({
  item,
  onOpen,
  selected,
  state,
  profileMatch,
}: {
  item: QueueItem
  onOpen: (i: QueueItem) => void
  selected?: boolean
  state?: CardState
  profileMatch?: ProfileRankPick
}) {
  const [stage, setStage] = useState<ImageStage>('cover')

  const handleClick = (e: MouseEvent<HTMLDivElement>) => {
    if ((e.target as HTMLElement).closest('a')) return
    onOpen(item)
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== 'Enter' && e.key !== ' ') return
    e.preventDefault()
    onOpen(item)
  }

  const interactiveProps = {
    role: 'button',
    tabIndex: 0,
    'aria-pressed': selected ?? false,
    onClick: handleClick,
    onKeyDown: handleKeyDown,
  } as const

  const handleImageError = () => {
    if (stage === 'cover') {
      setStage(item.preview_url ? 'preview' : 'fallback')
    } else if (stage === 'preview') {
      setStage('fallback')
    }
  }

  // The only profile-match signal on a card: a quiet theme tag, no score. The
  // number ("match 0.73") read as noise; the theme is the useful part.
  const themeTag = profileMatch ? (
    <span
      className="profile-theme-tag"
      aria-label={`Profile match: ${profileMatch.theme}`}
      title={`Matched ${profileMatch.theme}`}
    >
      {profileMatch.theme}
    </span>
  ) : null

  if (item.source === 'imessage') {
    return (
      <div className={cardClassName(selected, state, Boolean(profileMatch))} data-cursor-target="" {...interactiveProps}>
        <PixelBloom />
        <div className="textcard">
          <p>{item.text}</p>
          <div className="textcard-foot">
            <span>{item.author}</span>
            {themeTag}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className={cardClassName(selected, state, Boolean(profileMatch))} data-cursor-target="" {...interactiveProps}>
      <PixelBloom />
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
          {themeTag}
        </div>
      </div>
    </div>
  )
}
