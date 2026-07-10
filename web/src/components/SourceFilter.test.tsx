import { render, screen, fireEvent } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import { SourceFilter } from './SourceFilter'

test('toggles source', () => {
  const onChange = vi.fn()
  const { rerender } = render(<SourceFilter value={undefined} onChange={onChange} />)
  fireEvent.click(screen.getByText('youtube'))
  expect(onChange).toHaveBeenCalledWith('youtube')
  rerender(<SourceFilter value="youtube" onChange={onChange} />)
  fireEvent.click(screen.getByText('youtube'))
  expect(onChange).toHaveBeenCalledWith(undefined)
})
