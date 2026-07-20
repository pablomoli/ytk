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

test('italic text renders an em element', () => {
  const { container } = render(<>{renderInline('from the *current* model')}</>)
  const em = container.querySelector('em')
  expect(em?.textContent).toBe('current')
  expect(container.textContent).toBe('from the current model')
})

test('double-star bold is not mangled by the italic branch', () => {
  const { container } = render(<>{renderInline('**bold** not *italic* mixed')}</>)
  expect(container.querySelector('strong')?.textContent).toBe('bold')
  expect(container.querySelector('em')?.textContent).toBe('italic')
})

test('snake_case identifiers are left untouched (no underscore italic)', () => {
  const { container } = render(<>{renderInline('call depth_anything_v3 now')}</>)
  expect(container.querySelector('em')).toBeNull()
  expect(container.textContent).toBe('call depth_anything_v3 now')
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
