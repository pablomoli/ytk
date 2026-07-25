import { useEffect, useRef } from "react";
import { DUR, ScrollTrigger, SplitText, gsap, reducedMotion } from "../lib/motion";

/* Restrained focus-rack for bounded prose: profile portrait only. Not for
   note transcripts — SplitText on thousand-word content is a perf hazard,
   which is why this takes a single paragraph string.

   The reveal is timed, and scroll only decides WHEN it starts. A scrubbed
   reveal instead samples its progress from scroll position, which makes the
   readable end state contingent on scroll distance the layout never owed it:
   an element can only travel up the viewport as far as the content below it
   allows, so trailing paragraphs — with nothing beneath them — never reached
   the end condition and stayed dimmed forever (#124). A timed tween always
   completes, whatever the page's height. */
export function ScrollReveal({ children }: { children: string }) {
  const ref = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el || reducedMotion()) return;
    let split: InstanceType<typeof SplitText> | undefined;
    let trigger: ScrollTrigger | undefined;
    let tween: ReturnType<typeof gsap.from> | undefined;
    let cancelled = false;

    void (document.fonts?.ready ?? Promise.resolve()).then(() => {
      if (cancelled || !el.isConnected) return;
      try {
        split = SplitText.create(el, { type: "words", aria: "auto" });
        /* Reverting restores the plain text node React owns, so no inline
           opacity or blur can outlive the reveal that wrote it. */
        const settle = () => {
          split?.revert();
          split = undefined;
        };
        tween = gsap.from(split.words, {
          opacity: 0.25,
          filter: "blur(4px)",
          rotate: 1,
          duration: DUR.morph,
          stagger: DUR.reveal / Math.max(8, split.words.length),
          ease: "none",
          paused: true,
          onComplete: settle,
        });
        if (el.getBoundingClientRect().top < window.innerHeight) {
          /* Already on screen: reveal now. Waiting for a scroll the reader
             may never make is what left this prose unreadable. */
          tween.play();
        } else {
          trigger = ScrollTrigger.create({
            trigger: el,
            start: "top bottom",
            once: true,
            onEnter: () => tween?.play(),
          });
        }
      } catch {
        /* degraded state: static prose */
      }
    });

    return () => {
      cancelled = true;
      trigger?.kill();
      tween?.kill();
      split?.revert();
    };
  }, [children]);

  return <p ref={ref}>{children}</p>;
}
