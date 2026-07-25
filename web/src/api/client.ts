import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, refetchOnWindowFocus: false } },
});

export class ApiError extends Error {
  readonly path: string;
  readonly status: number;
  readonly body: unknown;
  constructor(path: string, status: number, body: unknown) {
    super(`${path} -> ${status}`);
    this.path = path;
    this.status = status;
    this.body = body;
  }
}

async function apiError(path: string, res: Response): Promise<ApiError> {
  let body: unknown;
  try {
    body = await res.json();
  } catch {
    body = await res.text();
  }
  return new ApiError(path, res.status, body);
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw await apiError(path, res);
  return res.json() as Promise<T>;
}

export async function apiSend<T>(path: string, method: string, body?: unknown): Promise<T> {
  // Built up rather than passed inline: under exactOptionalPropertyTypes an
  // explicit `undefined` is not the same as an absent key, and RequestInit
  // declares body/headers as optional-without-undefined. Truthiness check kept
  // as-is so a falsy body still sends no payload.
  const init: RequestInit = { method };
  if (body) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(body);
  }
  const res = await fetch(path, init);
  if (!res.ok) throw await apiError(path, res);
  return res.json() as Promise<T>;
}
