import { fireEvent, render, screen } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
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

test('applies the selected class when selected is true', () => {
  const { container } = render(
    <Card item={{ url: 'u', source: 'youtube', text: 'Hello' }} onOpen={() => {}} selected />,
  )
  expect(container.querySelector('.card')).toHaveClass('selected')
})

test('applies the ingesting class and renders a spinner when ingesting', () => {
  const { container } = render(
    <Card item={{ url: 'u', source: 'youtube', text: 'Hello' }} onOpen={() => {}} state="ingesting" />,
  )
  expect(container.querySelector('.card')).toHaveClass('ingesting')
  expect(container.querySelector('.spinner')).not.toBeNull()
})

test('applies the queued class without a selected outline', () => {
  const { container } = render(
    <Card item={{ url: 'u', source: 'youtube', text: 'Hello' }} onOpen={() => {}} state="queued" />,
  )
  expect(container.querySelector('.card')).toHaveClass('queued')
  expect(container.querySelector('.card')).not.toHaveClass('selected')
})

test('highlights a profile-ranked card with its score and theme', () => {
  const { container } = render(
    <Card
      item={{ url: 'u', source: 'tiktok', text: 'Shader sketch' }}
      onOpen={() => {}}
      profileMatch={{
        url: 'u',
        title: 'Shader sketch',
        source: 'tiktok',
        theme: 'Creative coding',
        score: 0.731,
      }}
    />,
  )
  expect(container.querySelector('.card')).toHaveClass('profile-match')
  expect(screen.getByText('match 0.73')).toBeInTheDocument()
  expect(screen.getByText('Creative coding')).toBeInTheDocument()
})

test('selects a card with the keyboard', () => {
  const onOpen = vi.fn()
  render(<Card item={{ url: 'u', source: 'youtube', text: 'Hello' }} onOpen={onOpen} />)

  fireEvent.keyDown(screen.getByRole('button'), { key: 'Enter' })
  fireEvent.keyDown(screen.getByRole('button'), { key: ' ' })

  expect(onOpen).toHaveBeenCalledTimes(2)
})
