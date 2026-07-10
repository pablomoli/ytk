import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'
import { Card } from './Card'

test('renders a youtube card with title and source badge', () => {
  render(<Card item={{ url: 'u', source: 'youtube', text: 'Hello' }} onOpen={() => {}} />)
  expect(screen.getByText('Hello')).toBeInTheDocument()
  expect(screen.getByTestId('card-source')).toHaveTextContent('youtube')
})

test('renders an imessage item as a text card without an image', () => {
  render(
    <Card
      item={{ url: 'u', source: 'imessage', text: 'note body', author: 'me' }}
      onOpen={() => {}}
    />,
  )
  expect(screen.getByText('note body')).toBeInTheDocument()
  expect(screen.getByText('me')).toBeInTheDocument()
  expect(screen.queryByRole('img')).not.toBeInTheDocument()
})

test('renders a media card with an image sourced from /api/cover', () => {
  const { container } = render(
    <Card item={{ url: 'u', source: 'youtube', text: 'Hello' }} onOpen={() => {}} />,
  )
  const img = container.querySelector('img')
  expect(img).not.toBeNull()
  expect(img).toHaveAttribute('src', expect.stringContaining('/api/cover'))
})
