import { useEffect, useRef } from 'react'
import { gsap, reducedMotion } from '../lib/motion'

const IDLE = 18 // half-size of the idle reticle box, px
const PAD = 6   // bracket overshoot around an acquired target

/* Brass viewfinder: four corner brackets follow the pointer; hovering a
   [data-cursor-target] element expands the brackets around it. Owned
   rewrite of the reactbits Target Cursor: no blend mode, no idle spin,
   house ease only. Native cursor is preserved over text and inputs. */
export function TargetCursor() {
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const root = rootRef.current
    if (!root || reducedMotion()) return
    const corners = [...root.children] as HTMLElement[]
    const xTo = gsap.quickTo(root, 'x', { duration: 0.12, ease: 'house' })
    const yTo = gsap.quickTo(root, 'y', { duration: 0.12, ease: 'house' })
    let acquired: HTMLElement | null = null

    const place = (w: number, h: number) => {
      const positions = [
        { x: -w / 2, y: -h / 2 }, { x: w / 2, y: -h / 2 },
        { x: -w / 2, y: h / 2 }, { x: w / 2, y: h / 2 },
      ]
      corners.forEach((corner, i) => gsap.to(corner, { x: positions[i].x, y: positions[i].y, duration: 0.18, ease: 'house' }))
    }

    const move = (event: MouseEvent) => {
      if (acquired) {
        const rect = acquired.getBoundingClientRect()
        xTo(rect.left + rect.width / 2)
        yTo(rect.top + rect.height / 2)
        place(rect.width + PAD * 2, rect.height + PAD * 2)
      } else {
        xTo(event.clientX)
        yTo(event.clientY)
      }
      const overText = (event.target as HTMLElement).closest('input, textarea, [contenteditable], pre, .note-panel')
      root.style.opacity = overText ? '0' : '1'
    }
    const over = (event: MouseEvent) => {
      const target = (event.target as HTMLElement).closest<HTMLElement>('[data-cursor-target]')
      if (target === acquired) return
      acquired = target
      if (!acquired) place(IDLE * 2, IDLE * 2)
    }

    place(IDLE * 2, IDLE * 2)
    addEventListener('mousemove', move)
    addEventListener('mouseover', over)
    return () => { removeEventListener('mousemove', move); removeEventListener('mouseover', over) }
  }, [])

  if (reducedMotion()) return null

  return (
    <div ref={rootRef} className="target-cursor" aria-hidden="true">
      <i /><i /><i /><i />
    </div>
  )
}
