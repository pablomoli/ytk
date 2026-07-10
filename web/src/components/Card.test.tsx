import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'
import { Card } from './Card'

test('renders a youtube card with title and source badge', () => {
  render(<Card item={{ url: 'u', source: 'youtube', text: 'Hello' }} onOpen={() => {}} />)
  expect(screen.getByText('Hello')).toBeInTheDocument()
  expect(screen.getByTestId('card-source')).toHaveTextContent('youtube')
})
