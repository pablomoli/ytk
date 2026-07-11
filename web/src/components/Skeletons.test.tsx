import { render } from '@testing-library/react'
import { expect, test } from 'vitest'
import { Skeletons } from './Skeletons'

test('renders N skeletons', () => {
  const { container } = render(<Skeletons count={5} />)
  expect(container.querySelectorAll('.skel')).toHaveLength(5)
})
