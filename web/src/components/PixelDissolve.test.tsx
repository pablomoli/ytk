import { render, act } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import { PixelDissolve } from './PixelDissolve'

test('renders a deterministic cell grid and completes', () => {
  vi.useFakeTimers()
  const onDone = vi.fn()
  vi.stubGlobal('ResizeObserver', class { observe() {}; disconnect() {}; unobserve() {} })
  Object.defineProperty(HTMLElement.prototype, 'clientWidth', { configurable: true, value: 280 })
  Object.defineProperty(HTMLElement.prototype, 'clientHeight', { configurable: true, value: 140 })
  const { container } = render(<PixelDissolve seedKey="sources/x.md" onDone={onDone} />)
  const cells = container.querySelectorAll('.pixel-dissolve i')
  expect(cells.length).toBe(50) // 280/28 -> 10 cols, 140/28 -> 5 rows
  act(() => { vi.runAllTimers() })
  expect(onDone).toHaveBeenCalledTimes(1)
  Reflect.deleteProperty(HTMLElement.prototype, 'clientWidth')
  Reflect.deleteProperty(HTMLElement.prototype, 'clientHeight')
  vi.unstubAllGlobals()
  vi.useRealTimers()
})
