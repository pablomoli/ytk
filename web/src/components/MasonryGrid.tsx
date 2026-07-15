import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { columnSpec, computeMasonryLayout } from '../lib/masonry'
import '../styles.css'

const GAP = 12
const COL_MIN = 190
const WIDE_RATIO = 1.3

/* A landscape cover means the card should tile two columns wide. Marked on
   the DOM (not React state) so the layout pass can read it synchronously. */
function markWide(img: HTMLImageElement) {
  if (!img.naturalWidth || !img.naturalHeight) return
  const card = img.closest<HTMLElement>('.card')
  if (!card) return
  if (img.naturalWidth / img.naturalHeight >= WIDE_RATIO) card.dataset.wide = '1'
}

export function MasonryGrid({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const grid = ref.current
    if (!grid) return

    let raf = 0
    const relayout = () => {
      if (raf) return
      raf = requestAnimationFrame(() => {
        raf = 0
        const width = grid.clientWidth
        if (!width) return
        const items = [...grid.children].filter(
          (el): el is HTMLElement => el instanceof HTMLElement,
        )
        /* Two passes because height depends on width: first size every card
           for its span, then measure and place. Cards are absolutely
           positioned with explicit widths, so offsetHeight reflects content
           at that width and relayout stays idempotent (no ratchet). */
        const { nCols, colW } = columnSpec(width, GAP, COL_MIN)
        items.forEach((el) => {
          const wide = el.dataset.wide === '1' && nCols >= 2
          el.style.width = `${wide ? 2 * colW + GAP : colW}px`
        })
        const boxes = items.map((el) => ({
          height: el.offsetHeight,
          wide: el.dataset.wide === '1',
        }))
        const layout = computeMasonryLayout(boxes, { width, gap: GAP, colMin: COL_MIN })
        items.forEach((el, i) => {
          el.style.left = `${layout.placed[i].left}px`
          el.style.top = `${layout.placed[i].top}px`
          el.style.width = `${layout.placed[i].width}px`
        })
        grid.style.height = `${layout.height}px`
      })
    }

    relayout()

    const ro = new ResizeObserver(relayout)
    ro.observe(grid)

    const onLoad = (e: Event) => {
      markWide(e.target as HTMLImageElement)
      relayout()
    }
    const images = [...grid.querySelectorAll('img')]
    images.forEach((img) => {
      if (img.complete) markWide(img)
      img.addEventListener('load', onLoad)
    })

    return () => {
      ro.disconnect()
      images.forEach((img) => img.removeEventListener('load', onLoad))
      if (raf) cancelAnimationFrame(raf)
    }
  })

  return (
    <main ref={ref} className="masonry">
      {children}
    </main>
  )
}
