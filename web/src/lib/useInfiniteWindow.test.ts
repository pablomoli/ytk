import { expect, test } from 'vitest'
import { nextCount } from './useInfiniteWindow'

test('nextCount grows by step, clamped to total', () => {
  expect(nextCount(60, 744, 60)).toBe(120)
  expect(nextCount(720, 744, 60)).toBe(744)
})
