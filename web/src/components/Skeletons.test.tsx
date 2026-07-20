import { render } from '@testing-library/react'
import { expect, test } from 'vitest'
import { Skeletons } from './Skeletons'

test('renders N card-shaped skeletons', () => {
  const { container } = render(<Skeletons count={5} />)
  expect(container.querySelectorAll('.skel')).toHaveLength(5)
  expect(container.querySelectorAll('.skel-thumb').length).toBeGreaterThan(0)
  expect(container.querySelectorAll('.skel-line')).toHaveLength(10) // title + meta per card
})
