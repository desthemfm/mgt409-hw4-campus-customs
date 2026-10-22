export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="status-msg" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      {label}
    </div>
  )
}

export function ErrorMessage({ message }: { message: string }) {
  return (
    <div className="status-msg status-error" role="alert">
      {message}
    </div>
  )
}
