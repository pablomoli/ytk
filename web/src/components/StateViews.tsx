export const EmptyState = ({ label }: { label: string }) => <div className="empty">{label}</div>

export const ErrorState = ({ error }: { error: unknown }) => (
  <div className="empty">failed to load: {String(error)}</div>
)
