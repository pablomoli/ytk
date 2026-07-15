import { render } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import { MasonryGrid } from './MasonryGrid'

test('writes absolute inline positioning onto every child', () => {
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      disconnect() {}
      unobserve() {}
    },
  )
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
    cb(0)
    return 1
  })
  // jsdom reports clientWidth 0, which makes relayout bail before it writes
  // any styles. Stub it on the prototype so it's in place before the effect
  // runs its first (synchronous, via the stubbed rAF) layout pass.
  Object.defineProperty(HTMLElement.prototype, 'clientWidth', {
    configurable: true,
    value: 802,
  })

  const { container } = render(
    <MasonryGrid>
      <div className="card">a</div>
      <div className="card">b</div>
      <div className="skel" />
    </MasonryGrid>,
  )

  const grid = container.querySelector('.masonry') as HTMLElement
  expect(grid.style.height).toMatch(/px$/)
  for (const el of grid.children) {
    const style = (el as HTMLElement).style
    expect(style.position).toBe('absolute')
    expect(style.left).toMatch(/px$/)
    expect(style.top).toMatch(/px$/)
    expect(style.width).toMatch(/px$/)
  }

  Reflect.deleteProperty(HTMLElement.prototype, 'clientWidth')
  vi.unstubAllGlobals()
})
