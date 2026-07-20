import { createElement, useEffect, useRef } from 'react'
import { DUR, SplitText, gsap, reducedMotion } from '../lib/motion'

/* Word-level baseline-rise stagger for display headings. Word-level (not
   chars) dodges the italic-Newsreader kerning shift; splitting waits for
   fonts.ready so metrics are final. SplitText reverts on cleanup, so the
   DOM returns to the plain string React owns. */
export function SplitHeading({ as = 'h1', children }: { as?: 'h1' | 'h2' | 'h3'; children: string }) {
  const ref = useRef<HTMLHeadingElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el || reducedMotion()) return
    let split: InstanceType<typeof SplitText> | undefined
    let cancelled = false
    void (document.fonts?.ready ?? Promise.resolve()).then(() => {
      if (cancelled || !el.isConnected) return
      try {
        split = SplitText.create(el, { type: 'words', aria: 'auto' })
        gsap.from(split.words, {
          y: '0.55em',
          opacity: 0,
          duration: DUR.morph,
          stagger: DUR.reveal / Math.max(6, split.words.length * 2),
        })
      } catch {
        /* jsdom or an exotic layout can refuse the split — the heading
           simply stays static, which is the correct degraded state */
      }
    })
    return () => { cancelled = true; split?.revert() }
  }, [children])

  return createElement(as, { ref }, children)
}
