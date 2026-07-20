import { gsap } from 'gsap'
import { CustomEase } from 'gsap/CustomEase'
import { Flip } from 'gsap/Flip'
import { ScrambleTextPlugin } from 'gsap/ScrambleTextPlugin'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { SplitText } from 'gsap/SplitText'

/* The single gsap import point for the app. Everything animates on the
   house ease (theme.css --ease) in one of four sanctioned registers.
   Rule: no other file imports 'gsap' — import from here. */
gsap.registerPlugin(CustomEase, Flip, ScrambleTextPlugin, ScrollTrigger, SplitText)

CustomEase.create('house', '0.25,0.1,0.25,1')
export const HOUSE_EASE = 'house'

export const DUR = { base: 0.18, morph: 0.3, wipe: 0.4, reveal: 0.6 } as const

gsap.defaults({ ease: HOUSE_EASE, duration: DUR.base })

/* theme.css kills CSS animation under prefers-reduced-motion, but GSAP
   writes inline styles the kill-switch cannot reach — every JS animation
   must check this and jump to its end state instead. */
export const reducedMotion = () =>
  typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

export { Flip, ScrollTrigger, SplitText, gsap }
