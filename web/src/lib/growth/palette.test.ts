import { expect, test } from 'vitest'
import { kmeansPalette } from './palette'

function block(r: number, g: number, b: number, n: number): number[] {
  return Array.from({ length: n }, () => [r, g, b, 255]).flat()
}

test('recovers dominant colors from synthetic pixels', () => {
  const pixels = new Uint8ClampedArray([
    ...block(200, 40, 30, 600),
    ...block(20, 30, 40, 300),
    ...block(240, 230, 210, 100),
  ])
  const palette = kmeansPalette(pixels, 3)
  expect(palette).toHaveLength(3)
  expect(palette[0]).toMatch(/^#[0-9a-f]{6}$/)
  const red = parseInt(palette[0].slice(1, 3), 16)
  expect(red).toBeGreaterThan(150)
})

test('deterministic across calls', () => {
  const pixels = new Uint8ClampedArray(block(10, 200, 100, 500).concat(block(90, 10, 200, 500)))
  expect(kmeansPalette(pixels, 4)).toEqual(kmeansPalette(pixels, 4))
})

test('handles fewer distinct colors than k', () => {
  const pixels = new Uint8ClampedArray(block(50, 50, 50, 64))
  const palette = kmeansPalette(pixels, 5)
  expect(palette).toHaveLength(5)
})
