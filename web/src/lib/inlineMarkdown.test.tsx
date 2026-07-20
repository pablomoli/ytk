import { render } from '@testing-library/react'
import { expect, test } from 'vitest'
import { renderInline } from './inlineMarkdown'

test('bold text renders a strong element', () => {
  const { container } = render(<>{renderInline('**x**')}</>)
  const strong = container.querySelector('strong')
  expect(strong).not.toBeNull()
  expect(strong?.textContent).toBe('x')
})

test('markdown link renders an anchor with href and text', () => {
  const { container } = render(<>{renderInline('[a](http://b)')}</>)
  const anchor = container.querySelector('a')
  expect(anchor).not.toBeNull()
  expect(anchor?.getAttribute('href')).toBe('http://b')
  expect(anchor?.textContent).toBe('a')
  expect(anchor?.getAttribute('target')).toBe('_blank')
  expect(anchor?.getAttribute('rel')).toBe('noreferrer')
})

test('plain text passes through unchanged', () => {
  const { container } = render(<>{renderInline('just plain text')}</>)
  expect(container.textContent).toBe('just plain text')
  expect(container.querySelector('strong')).toBeNull()
  expect(container.querySelector('a')).toBeNull()
})

test('a line mixing bold and a link renders both', () => {
  const { container } = render(<>{renderInline('see **this** and [link](https://x.com)')}</>)
  const strong = container.querySelector('strong')
  const anchor = container.querySelector('a')
  expect(strong?.textContent).toBe('this')
  expect(anchor?.textContent).toBe('link')
  expect(anchor?.getAttribute('href')).toBe('https://x.com')
  expect(container.textContent).toBe('see this and link')
})
