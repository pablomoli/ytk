import { render } from '@testing-library/react'
import { expect, test } from 'vitest'
import { PixelBloom } from './PixelBloom'

test('renders an aria-hidden canvas layer', () => {
  const { container } = render(<div style={{ position: 'relative' }}><PixelBloom /></div>)
  const canvas = container.querySelector('canvas.pixel-bloom')
  expect(canvas).toBeInTheDocument()
  expect(canvas).toHaveAttribute('aria-hidden', 'true')
})
