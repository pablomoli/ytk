import { ApiError } from '../api/client'

export const EmptyState = ({ label }: { label: string }) => <div className="empty">{label}</div>

export const ErrorState = ({ error }: { error: unknown }) => {
  const detail = error instanceof ApiError && typeof error.body === 'object' && error.body && 'detail' in error.body
    ? String(error.body.detail)
    : String(error)
  return <div className="empty">failed to load: {detail}</div>
}
