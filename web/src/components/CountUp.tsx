import { useEffect, useRef } from 'react'
import { DUR, gsap, reducedMotion } from '../lib/motion'

const fmt = new Intl.NumberFormat('en-US')

/* Number settles onto its new reading instead of flipping. First render is
   instant; only CHANGES tween. React renders the final value, the tween
   perturbs textContent in between (self-correcting on re-render). */
export function CountUp({ value }: { value: number }) {
  const ref = useRef<HTMLSpanElement>(null)
  const shown = useRef<number>(undefined)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const from = shown.current
    shown.current = value
    if (from === undefined || from === value || reducedMotion()) { el.textContent = fmt.format(value); return }
    const counter = { n: from }
    const tween = gsap.to(counter, {
      n: value,
      duration: DUR.wipe,
      onUpdate: () => { el.textContent = fmt.format(Math.round(counter.n)) },
    })
    return () => { tween.kill(); el.textContent = fmt.format(value) }
  }, [value])

  return <span ref={ref}>{fmt.format(value)}</span>
}
