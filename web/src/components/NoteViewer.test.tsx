import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeAll, expect, test, vi } from 'vitest'
import type { FreshNote } from '../api/fresh'
import { NoteViewer } from './NoteViewer'

beforeAll(() => {
  HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) { this.open = true }
  HTMLDialogElement.prototype.close ??= function (this: HTMLDialogElement) { this.open = false; this.dispatchEvent(new Event('close')) }
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

test('close button and dialog close event both call onClose', () => {
  const onClose = vi.fn()
  wrap(<NoteViewer note={note} onClose={onClose} />)
  fireEvent.click(screen.getByRole('button', { name: 'close', hidden: true }))
  expect(onClose).toHaveBeenCalledTimes(1)
})
