import { renderHook } from '@testing-library/react'
import { expect, test } from 'vitest'
import { useHoverDecode } from './useHoverDecode'

test('returns a stable mouseenter handler', () => {
  const { result, rerender } = renderHook(() => useHoverDecode())
  const first = result.current.onMouseEnter
  rerender()
  expect(result.current.onMouseEnter).toBe(first)
  expect(typeof first).toBe('function')
})
