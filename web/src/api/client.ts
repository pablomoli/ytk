import { QueryClient } from '@tanstack/react-query'

export const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, refetchOnWindowFocus: false } },
})

export class ApiError extends Error {
  constructor(
    public readonly path: string,
    public readonly status: number,
    public readonly body: unknown,
  ) {
    super(`${path} -> ${status}`)
  }
}

async function apiError(path: string, res: Response): Promise<ApiError> {
  let body: unknown
  try {
    body = await res.json()
  } catch {
    body = await res.text()
  }
  return new ApiError(path, res.status, body)
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(path)
  if (!res.ok) throw await apiError(path, res)
  return res.json() as Promise<T>
}

export async function apiSend<T>(path: string, method: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw await apiError(path, res)
  return res.json() as Promise<T>
}
