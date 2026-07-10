import { fireEvent, render, screen } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import { FreshCard } from './FreshCard'

const note = {
  path: 'sources/video.md',
  stem: 'video',
  title: 'A video',
  url: 'https://example.com/video',
  source: 'youtube',
  added: '2026-07-10',
  thumbnail: 'images/video.jpg',
  tags: ['reference'],
  has_take: true,
}

test('uses vault media for fresh-note thumbnails', () => {
  const { container } = render(<FreshCard note={note} onOpen={() => {}} onDelete={() => {}} />)

  expect(container.querySelector('img')).toHaveAttribute('src', '/vault-media/images/video.jpg')
  expect(screen.getByText('#reference')).toBeInTheDocument()
})

test('opens through its button and keeps external links separate', () => {
  const onOpen = vi.fn()
  render(<FreshCard note={note} onOpen={onOpen} onDelete={() => {}} />)

  fireEvent.click(screen.getByRole('button', { name: 'open note' }))
  fireEvent.click(screen.getByRole('link', { name: 'open' }))

  expect(onOpen).toHaveBeenCalledTimes(1)
})

test('renders memos as text cards without a vault image', () => {
  render(
    <FreshCard
      note={{ ...note, source: 'memo', preview: 'A captured thought', thumbnail: null, kind: 'thought' }}
      onOpen={() => {}}
      onDelete={() => {}}
    />,
  )

  expect(screen.getByText('A captured thought')).toBeInTheDocument()
  expect(screen.queryByRole('img')).not.toBeInTheDocument()
})
