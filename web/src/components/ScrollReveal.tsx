import { useEffect, useRef } from 'react'
import { ScrollTrigger, SplitText, gsap, reducedMotion } from '../lib/motion'

/* Restrained focus-rack for bounded prose: profile portrait only. Not for
   note transcripts — SplitText on thousand-word content is a perf hazard,
   which is why this takes a single paragraph string. */
export function ScrollReveal({ children }: { children: string }) {
  const ref = useRef<HTMLParagraphElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el || reducedMotion()) return
    let split: InstanceType<typeof SplitText> | undefined
    let trigger: ScrollTrigger | undefined
    let cancelled = false
    void (document.fonts?.ready ?? Promise.resolve()).then(() => {
      if (cancelled || !el.isConnected) return
      try {
        split = SplitText.create(el, { type: 'words', aria: 'auto' })
        const tween = gsap.fromTo(split.words,
          { opacity: 0.25, filter: 'blur(4px)', rotate: 1 },
          { opacity: 1, filter: 'blur(0px)', rotate: 0, stagger: 0.02, ease: 'none' })
        trigger = ScrollTrigger.create({ trigger: el, start: 'top 85%', end: 'top 40%', scrub: true, animation: tween })
      } catch {
        /* degraded state: static prose */
      }
    })
    return () => { cancelled = true; trigger?.kill(); split?.revert() }
  }, [children])

  return <p ref={ref}>{children}</p>
}
