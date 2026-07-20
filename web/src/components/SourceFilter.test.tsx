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

test('renders the discovery sources as filter chips', () => {
  const onChange = vi.fn()
  render(<SourceFilter value={undefined} onChange={onChange} />)
  for (const s of ['tiktok', 'reddit', 'instagram', 'youtube']) {
    fireEvent.click(screen.getByText(s))
    expect(onChange).toHaveBeenCalledWith(s)
  }
})

test('chips carry aria-pressed reflecting selection', () => {
  const { rerender } = render(<SourceFilter value={undefined} onChange={() => {}} />)
  expect(screen.getByRole('button', { name: 'youtube' })).toHaveAttribute('aria-pressed', 'false')
  rerender(<SourceFilter value="youtube" onChange={() => {}} />)
  expect(screen.getByRole('button', { name: 'youtube' })).toHaveAttribute('aria-pressed', 'true')
})
