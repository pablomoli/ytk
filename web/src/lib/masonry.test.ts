import { expect, test } from 'vitest'
import { spanFor } from './masonry'

test('spanFor computes row span from height', () => {
  expect(spanFor(200)).toBe(Math.ceil((200 + 12) / (8 + 12)))
})

test('spanFor honors custom rowH and gap', () => {
  expect(spanFor(100, 10, 5)).toBe(Math.ceil((100 + 5) / (10 + 5)))
})

test('spanFor rounds up partial rows', () => {
  expect(spanFor(1)).toBe(1)
})
