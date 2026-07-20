import { render, screen, fireEvent } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import { EmptyState, ErrorState } from './StateViews'

test('empty state shows glyph, label, and optional hint', () => {
  const { container } = render(<EmptyState label="nothing ingested yet" hint="paste urls in the inbox to begin" />)
  expect(container.querySelector('.state-glyph')).toBeInTheDocument()
  expect(screen.getByText('nothing ingested yet')).toBeInTheDocument()
  expect(screen.getByText('paste urls in the inbox to begin')).toBeInTheDocument()
})

test('error state offers retry when handler given', () => {
  const onRetry = vi.fn()
  render(<ErrorState error={new Error('boom')} onRetry={onRetry} />)
  fireEvent.click(screen.getByRole('button', { name: 'retry' }))
  expect(onRetry).toHaveBeenCalledTimes(1)
})
