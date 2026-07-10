import { expect, test, vi } from 'vitest'
import { apiGet } from './client'

test('apiGet returns parsed json', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify([{ path: 'a' }]), { status: 200 })))
  const data = await apiGet<{ path: string }[]>('/api/fresh?n=1')
  expect(data[0].path).toBe('a')
})

test('apiGet throws on non-2xx', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response('nope', { status: 500 })))
  await expect(apiGet('/api/fresh')).rejects.toThrow()
})
