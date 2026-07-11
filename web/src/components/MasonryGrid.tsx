import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { spanFor } from '../lib/masonry'
import '../styles.css'

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
        const cards = [...grid.querySelectorAll<HTMLElement>('.card')]
        const spans = cards.map((c) => spanFor(c.scrollHeight))
        cards.forEach((c, i) => {
          c.style.gridRowEnd = `span ${spans[i]}`
        })
      })
    }

    relayout()

    const ro = new ResizeObserver(relayout)
    ro.observe(grid)

    const images = [...grid.querySelectorAll('img')]
    images.forEach((img) => img.addEventListener('load', relayout))

    return () => {
      ro.disconnect()
      images.forEach((img) => img.removeEventListener('load', relayout))
      if (raf) cancelAnimationFrame(raf)
    }
  })

  return (
    <main ref={ref} className="masonry">
      {children}
    </main>
  )
}
