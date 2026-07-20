import { StrictMode } from 'react'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeAll, expect, test, vi } from 'vitest'
import type { FreshNote } from '../api/fresh'
import { NoteViewer } from './NoteViewer'

beforeAll(() => {
  HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) { this.open = true }
  // Model the real browser: close() flips open synchronously but fires the
  // 'close' event on a queued task, not synchronously. A ref-flag guard set in
  // effect cleanup is already reset by StrictMode's remount before this event
  // arrives — which is why onClose must never be wired to the native close
  // event. The async dispatch here is what makes the StrictMode test below a
  // real reproduction rather than a false positive.
  HTMLDialogElement.prototype.close ??= function (this: HTMLDialogElement) {
    this.open = false
    queueMicrotask(() => this.dispatchEvent(new Event('close')))
  }
  vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response('{}'))))
})

const note: FreshNote = { path: 'sources/youtube/x.md', title: 'a note', source: 'youtube', tags: [], url: '', thumbnail: '', has_take: false } as unknown as FreshNote

const wrap = (ui: React.ReactElement) => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false, enabled: false } } })}>{ui}</QueryClientProvider>,
)

test('opens as a modal dialog labelled by the note title', () => {
  const showModal = vi.spyOn(HTMLDialogElement.prototype, 'showModal')
  wrap(<NoteViewer note={note} onClose={() => {}} />)
  expect(showModal).toHaveBeenCalled()
  expect(screen.getByRole('dialog', { hidden: true })).toHaveAccessibleName('a note')
})

test('close button calls onClose', () => {
  const onClose = vi.fn()
  wrap(<NoteViewer note={note} onClose={onClose} />)
  fireEvent.click(screen.getByRole('button', { name: 'close', hidden: true }))
  expect(onClose).toHaveBeenCalledTimes(1)
})

test('backdrop click calls onClose', () => {
  const onClose = vi.fn()
  const { container } = wrap(<NoteViewer note={note} onClose={onClose} />)
  fireEvent.click(container.querySelector('dialog')!)
  expect(onClose).toHaveBeenCalledTimes(1)
})

test('escape (cancel event) calls onClose', () => {
  const onClose = vi.fn()
  const { container } = wrap(<NoteViewer note={note} onClose={onClose} />)
  fireEvent(container.querySelector('dialog')!, new Event('cancel', { cancelable: true }))
  expect(onClose).toHaveBeenCalledTimes(1)
})

test('survives StrictMode double-mount without self-closing (async close event)', async () => {
  const onClose = vi.fn()
  // StrictMode must wrap QueryClientProvider (matching main.tsx's real nesting)
  // for React to actually double-invoke effects here; wrap() puts the query
  // client outermost, which suppresses the double-invoke in this renderer.
  render(
    <StrictMode>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false, enabled: false } } })}>
        <NoteViewer note={note} onClose={onClose} />
      </QueryClientProvider>
    </StrictMode>,
  )
  // Flush the close event the cleanup queued during the mount->cleanup->mount
  // cycle. A ref-flag guard would already be reset by the remount here, so
  // this asserts onClose is decoupled from the native close event entirely.
  await act(async () => { await Promise.resolve() })
  expect(onClose).not.toHaveBeenCalled()
  expect(screen.getByRole('dialog', { hidden: true })).toBeInTheDocument()
})
