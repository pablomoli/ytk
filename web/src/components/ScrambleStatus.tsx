import { useEffect, useRef } from 'react'
import { gsap, reducedMotion } from '../lib/motion'

const CHARSET = '.: abcdefghijklmnopqrstuvwxyz0123456789'

/* Instrument-readout text: on each discrete change the span decodes into
   the new reading. React renders the final text; the tween only perturbs
   the DOM in between, so a mid-tween re-render is self-correcting. The
   min-width lock keeps proportional Newsreader from jittering the rail. */
export function ScrambleStatus({ text, className }: { text: string; className?: string }) {
  const ref = useRef<HTMLSpanElement>(null)
  const prev = useRef<string>(undefined)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const changed = prev.current !== undefined && prev.current !== text
    prev.current = text
    if (!changed || reducedMotion()) return
    const tween = gsap.to(el, {
      duration: 0.5,
      scrambleText: { text, chars: CHARSET, speed: 0.4 },
    })
    return () => { tween.kill(); el.textContent = text }
  }, [text])

  return (
    <span ref={ref} className={`scramble-status${className ? ` ${className}` : ''}`} style={{ minWidth: `${text.length}ch` }}>
      {text}
    </span>
  )
}
