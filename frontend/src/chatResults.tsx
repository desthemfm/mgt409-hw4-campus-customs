// The concierge's latest search results, shared between the chat panel (which fills it)
// and the on-page results grid (which shows it). Problem 7: chat search that updates the page.

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import type { ProductSummary } from './api'

export type ChatResults = {
  id: number // changes on every new result, so the page can scroll and announce it
  heading: string
  question: string // the shopper's message that produced these results
  products: ProductSummary[]
}

type ChatResultsValue = {
  results: ChatResults | null
  show: (heading: string | null, question: string, products: ProductSummary[]) => void
  clear: () => void
}

const ChatResultsContext = createContext<ChatResultsValue | null>(null)

export function ChatResultsProvider({ children }: { children: ReactNode }) {
  const [results, setResults] = useState<ChatResults | null>(null)

  const show = useCallback((heading: string | null, question: string, products: ProductSummary[]) => {
    if (products.length === 0) return // nothing matched: leave the page as it is
    setResults((prev) => ({
      id: (prev?.id ?? 0) + 1,
      heading: heading || 'Concierge picks',
      question,
      products,
    }))
  }, [])

  const clear = useCallback(() => setResults(null), [])
  const value = useMemo(() => ({ results, show, clear }), [results, show, clear])
  return <ChatResultsContext.Provider value={value}>{children}</ChatResultsContext.Provider>
}

export function useChatResults() {
  const ctx = useContext(ChatResultsContext)
  if (!ctx) throw new Error('useChatResults must be used inside <ChatResultsProvider>')
  return ctx
}
