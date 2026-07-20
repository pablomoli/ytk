import { renderHook } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import { nextCount, useInfiniteWindow } from './useInfiniteWindow'

vi.stubGlobal('IntersectionObserver', class { observe() {}; disconnect() {}; unobserve() {} })

test('nextCount clamps to total', () => {
  expect(nextCount(60, 70, 60)).toBe(70)
})

test('new items array with same resetKey keeps the window (poll refetch)', () => {
  const { result, rerender } = renderHook(({ items }) => useInfiniteWindow(items, 2, 'all'), {
    initialProps: { items: ['a', 'b', 'c'] },
  })
  expect(result.current.visible).toEqual(['a', 'b'])
  rerender({ items: ['a', 'b', 'c', 'd'] }) // fresh array identity, same key
  expect(result.current.visible).toEqual(['a', 'b']) // window NOT reset (was the bug: identity reset)
})

test('resetKey change resets the window', () => {
  const { result, rerender } = renderHook(({ key }) => useInfiniteWindow(['a', 'b', 'c'], 2, key), {
    initialProps: { key: 'all' },
  })
  rerender({ key: 'youtube' })
  expect(result.current.visible).toEqual(['a', 'b'])
})
