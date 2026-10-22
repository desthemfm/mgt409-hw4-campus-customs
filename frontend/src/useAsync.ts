import { useEffect, useState } from 'react'

type AsyncState<T> = { data: T | null; error: string | null; loading: boolean }

// Runs an async loader whenever `deps` change, and cancels the previous request if it is still running.
export function useAsync<T>(load: (signal: AbortSignal) => Promise<T>, deps: unknown[]): AsyncState<T> {
  const [state, setState] = useState<AsyncState<T>>({ data: null, error: null, loading: true })

  useEffect(() => {
    const controller = new AbortController()
    setState((s) => ({ ...s, loading: true, error: null }))
    load(controller.signal)
      .then((data) => setState({ data, error: null, loading: false }))
      .catch((err: Error) => {
        if (err.name !== 'AbortError') setState({ data: null, error: err.message, loading: false })
      })
    return () => controller.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  return state
}
