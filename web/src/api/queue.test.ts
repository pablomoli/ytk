import { expect, test, vi } from 'vitest'
import { fetchQueue } from './queue'

test('fetchQueue returns items', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify({ items: [{ url: 'u', source: 'instagram' }] }), { status: 200 })),
  )
  const items = await fetchQueue()
  expect(Array.isArray(items)).toBe(true)
  expect(items[0].source).toBe('instagram')
})
