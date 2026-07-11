import { expect, test, vi } from 'vitest'
import { fetchFresh } from './fresh'

test('fetchFresh requests the fixed fresh-feed size', async () => {
  const fetch = vi.fn(async () => new Response(JSON.stringify([]), { status: 200 }))
  vi.stubGlobal('fetch', fetch)

  await expect(fetchFresh()).resolves.toEqual([])
  expect(fetch).toHaveBeenCalledWith('/api/fresh?n=60')
})
