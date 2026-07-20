import { useCallback, useEffect, useRef, useState } from 'react'

export const nextCount = (cur: number, total: number, step: number): number =>
  Math.min(cur + step, total)

export function useInfiniteWindow<T>(items: T[], step = 60, resetKey: unknown = null) {
  const [count, setCount] = useState(step)

  useEffect(() => {
    setCount(step)
  }, [resetKey, step])

  const obs = useRef<IntersectionObserver | null>(null)

  const sentinelRef = useCallback(
    (el: HTMLElement | null) => {
      obs.current?.disconnect()
      if (!el) return
      obs.current = new IntersectionObserver(entries => {
        if (entries[0].isIntersecting) {
          setCount(c => nextCount(c, items.length, step))
        }
      })
      obs.current.observe(el)
    },
    [items.length, step],
  )

  return { visible: items.slice(0, count), sentinelRef }
}
