import { expect, test } from 'vitest'
import { formatElapsed } from './elapsed'

test('formats whole seconds as m:ss with zero-padded seconds', () => {
  expect(formatElapsed(100, 88)).toBe('0:12')
  expect(formatElapsed(200, 88)).toBe('1:52')
  expect(formatElapsed(3661, 60)).toBe('60:01')
})

test('treats a missing/zero start as no reading', () => {
  expect(formatElapsed(100, 0)).toBe('')
  expect(formatElapsed(100, null)).toBe('')
})

test('clamps a fractional start timestamp to whole seconds', () => {
  // the reported bug: current_started = X.833319 rendered "0:12.166681..."
  expect(formatElapsed(100, 87.833319)).toBe('0:12')
  expect(formatElapsed(100.9, 88)).toBe('0:12')
})

test('empty string when no start; clamps negative to 0:00', () => {
  expect(formatElapsed(100)).toBe('')
  expect(formatElapsed(50, 100)).toBe('0:00')
})
