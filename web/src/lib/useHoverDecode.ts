import { useCallback } from 'react'
import type { MouseEvent as ReactMouseEvent } from 'react'
import { gsap, reducedMotion } from './motion'

const CHARSET = '.: abcdefghijklmnopqrstuvwxyz'

/* Short decode flicker on hover. Width/height are locked for the tween so
   layout never breathes; original text is restored on kill. Only safe on
   elements whose text is static between renders (chips, titles). */
export function useHoverDecode() {
  const onMouseEnter = useCallback((event: ReactMouseEvent<HTMLElement>) => {
    const el = event.currentTarget
    if (reducedMotion()) return
    const original = el.textContent ?? ''
    if (!original || original.length > 80) return
    const rect = el.getBoundingClientRect()
    el.style.width = `${rect.width}px`
    el.style.height = `${rect.height}px`
    gsap.to(el, {
      duration: 0.25,
      scrambleText: { text: original, chars: CHARSET, speed: 0.5 },
      onComplete: () => { el.style.width = ''; el.style.height = ''; el.textContent = original },
      onInterrupt: () => { el.style.width = ''; el.style.height = ''; el.textContent = original },
    })
  }, [])
  return { onMouseEnter }
}
