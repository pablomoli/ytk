import { DUR, reducedMotion } from './motion'

/* Pixelate wipe between two states of a canvas surface: freeze the old
   frame in an overlay, let the caller swap the live canvas, then dissolve
   the frozen frame through coarsening pixel blocks. The blocky dialect of
   the growth dither, applied to state changes. */
let active: HTMLCanvasElement | null = null

export function pixelateSwap(canvas: HTMLCanvasElement, swap: () => void, opts?: { duration?: number }): void {
  const duration = (opts?.duration ?? DUR.wipe) * 1000
  const w = canvas.width
  const h = canvas.height
  if (reducedMotion() || !w || !h || !canvas.parentElement) { swap(); return }

  active?.remove()
  const overlay = document.createElement('canvas')
  overlay.className = 'pixelate-overlay'
  overlay.width = w
  overlay.height = h
  const rect = canvas.getBoundingClientRect()
  const host = canvas.parentElement
  Object.assign(overlay.style, {
    position: 'absolute',
    left: `${canvas.offsetLeft}px`,
    top: `${canvas.offsetTop}px`,
    width: `${rect.width}px`,
    height: `${rect.height}px`,
    pointerEvents: 'none',
    imageRendering: 'pixelated',
  })
  const context = overlay.getContext('2d')
  if (!context) { swap(); return }
  try { context.drawImage(canvas, 0, 0) } catch { swap(); return }
  const frame = document.createElement('canvas') // untouched copy of the old state
  frame.width = w; frame.height = h
  frame.getContext('2d')?.drawImage(overlay, 0, 0)
  host.appendChild(overlay)
  active = overlay

  swap()

  const start = performance.now()
  const step = (now: number) => {
    if (active !== overlay) return
    const t = Math.min(1, (now - start) / duration)
    const eased = 0.5 - 0.5 * Math.cos(t * Math.PI) // house-adjacent, dependency-free
    const block = 1 + eased * 31
    const dw = Math.max(1, Math.round(w / block))
    const dh = Math.max(1, Math.round(h / block))
    context.imageSmoothingEnabled = false
    context.clearRect(0, 0, w, h)
    context.drawImage(frame, 0, 0, dw, dh)         // downsample
    context.drawImage(overlay, 0, 0, dw, dh, 0, 0, w, h) // upscale blocky
    overlay.style.opacity = `${1 - eased}`
    if (t < 1) requestAnimationFrame(step)
    else { overlay.remove(); if (active === overlay) active = null }
  }
  requestAnimationFrame(step)
}
