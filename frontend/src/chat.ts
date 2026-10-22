// Chat client for the floating chat panel. Talks to POST /api/chat on the FastAPI backend,
// where the PydanticAI agent (backend/agent.py) answers. Shapes mirror backend/models.py.

import type { ProductSummary } from './api'

export type ChatRole = 'user' | 'assistant'

export type ChatMessage = {
  id: string
  role: ChatRole
  content: string
  products?: ProductSummary[]
  resultsHeading?: string | null
  cartActions?: CartAction[]
}

// Mirrors CartAction in backend/models.py: a cart change the concierge made (Problem 9).
export type CartAction = {
  action: 'add' | 'remove'
  product_id: string
  size: string
  quantity: number
  name: string
  price: number
  image_url: string
  available: number
}

// What we tell the concierge about the browser cart.
export type CartLine = { product_id: string; size: string; quantity: number }

// Mirrors ChatReply in backend/models.py: what POST /api/chat returns.
export type ChatReply = {
  reply: string
  products: ProductSummary[]
  results_heading: string | null
  cart_actions: CartAction[]
}

type SavedMessage = {
  id: number
  role: ChatRole
  content: string
  products: ProductSummary[]
  created_at: string
}

const HISTORY_TO_SEND = 12

// Mirrors PageContext in backend/models.py: what the shopper is looking at. Only ids and
// labels; the backend looks every product up in the database itself.
export type PageContext = {
  path: string
  product_id: string | null
  category_filter: string | null
  results_heading: string | null
  result_product_ids: string[]
}

async function readError(res: Response): Promise<string> {
  const body = await res.json().catch(() => null)
  if (typeof body?.detail === 'string') return body.detail
  if (res.status === 422) return 'That message is too long. Please keep it under 1,000 characters.'
  return 'Something went wrong. Please try again.'
}

/**
 * Send one message to the concierge.
 * Signed-in shoppers: the backend loads and saves history itself (chat_messages table).
 * Guests: we send the recent conversation from this browser so the agent has context.
 */
// What the streaming endpoint sends while the concierge works (one JSON object per line).
export type StreamUpdate =
  | { type: 'status'; text: string } // e.g. "Checking sizes and stock…"
  | { type: 'delta'; reply: string } // the reply written so far (a draft until "done")
  | { type: 'reset' } // the honesty check sent the draft back to be rewritten

/**
 * Send one message to the concierge and stream the answer (Problem 9).
 * Calls onUpdate as the concierge searches and writes, then resolves with the checked final reply.
 * Signed-in shoppers: the backend loads and saves history itself (chat_messages table).
 * Guests: we send the recent conversation from this browser so the agent has context.
 */
export async function sendChatMessage(
  message: string,
  history: ChatMessage[],
  page: PageContext,
  cart: CartLine[],
  onUpdate: (update: StreamUpdate) => void = () => {},
): Promise<ChatReply> {
  let res: Response
  try {
    res = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({
        message,
        history: history
          .filter((m) => m.id !== 'greeting')
          .slice(-HISTORY_TO_SEND)
          .map(({ role, content }) => ({ role, content })),
        page,
        cart,
      }),
    })
  } catch {
    throw new Error("We couldn't reach the shop server. Please check your connection and try again.")
  }
  if (!res.ok || !res.body) throw new Error(await readError(res))

  // Read the NDJSON stream line by line as it arrives.
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffered = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffered += value
    const lines = buffered.split('\n')
    buffered = lines.pop() ?? ''
    for (const line of lines) {
      if (!line.trim()) continue
      const event = JSON.parse(line)
      if (event.type === 'done') return event as ChatReply
      if (event.type === 'error') throw new Error(event.detail)
      onUpdate(event as StreamUpdate)
    }
  }
  throw new Error('The connection closed before the answer finished. Please try again.')
}

/** A signed-in shopper's saved conversation (empty for guests). */
export async function fetchChatHistory(): Promise<ChatMessage[]> {
  const res = await fetch('/api/chat/history', { credentials: 'same-origin' })
  if (!res.ok) return []
  const saved = (await res.json()) as SavedMessage[]
  return saved.map((m) => ({ id: `saved-${m.id}`, role: m.role, content: m.content, products: m.products }))
}
