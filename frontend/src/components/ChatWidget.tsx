import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '../auth'
import { useCart } from '../cart'
import { formatPrice } from '../api'
import { fetchChatHistory, sendChatMessage, type CartAction, type ChatMessage, type PageContext, type StreamUpdate } from '../chat'
import { useChatResults } from '../chatResults'
import ChatText from './ChatText'

function greeting(firstName?: string): ChatMessage {
  return {
    id: 'greeting',
    role: 'assistant',
    content: firstName
      ? `Good to see you, ${firstName}. What can I help you find today?`
      : 'Good afternoon. Looking for something in particular? Ask me about our Yale merch, sizes, prices, or stock.',
  }
}

let nextId = 0
const newId = () => `m${++nextId}`

export default function ChatWidget() {
  const { user, checking } = useAuth()
  const { pathname, search } = useLocation()
  const chatResults = useChatResults()
  const cart = useCart()
  const resultsHiddenHere = ['/login', '/create-account', '/cart'].includes(pathname)
  const viewingProductId = pathname.match(/^\/products\/([^/]+)$/)?.[1] ?? null

  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState<ChatMessage[]>([greeting()])
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  // While the concierge works: what it's doing ("Checking sizes…") and the reply written so far.
  const [live, setLive] = useState<{ status: string; draft: string }>({ status: '', draft: '' })
  const [error, setError] = useState('')
  const listRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  // When someone signs in or out, start fresh: load their saved conversation, or a new guest chat.
  useEffect(() => {
    if (checking) return
    let cancelled = false
    setError('')
    if (!user) {
      setMessages([greeting()])
      return
    }
    fetchChatHistory().then((saved) => {
      if (!cancelled) setMessages([greeting(user.first_name), ...saved])
    })
    return () => {
      cancelled = true
    }
  }, [user, checking])

  // Jump straight to the newest message when the panel opens; glide when new messages arrive.
  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'auto' })
  }, [open])
  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, sending, live.draft])

  useEffect(() => {
    if (open) inputRef.current?.focus()
    // Lets the page leave room for the open panel so on-page results aren't hidden behind it.
    document.body.classList.toggle('chat-open', open)
  }, [open])

  // Apply the cart changes the concierge made (it checked live stock on the server first).
  function applyCartActions(actions: CartAction[]) {
    for (const a of actions) {
      if (a.action === 'add') {
        const { product_id, size, name, price, image_url } = a
        cart.add({ product_id, size, name, price, image_url }, a.quantity, a.available)
      } else {
        cart.setQuantity(a.product_id, a.size, cart.quantityOf(a.product_id, a.size) - a.quantity)
      }
    }
  }

  function viewOnPage() {
    if (window.matchMedia('(max-width: 860px)').matches) setOpen(false) // the panel covers the page on phones
    document.getElementById('concierge-results')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  async function send(e?: FormEvent) {
    e?.preventDefault()
    const text = draft.trim()
    if (!text || sending) return
    const userMsg: ChatMessage = { id: newId(), role: 'user', content: text }
    const history = messages
    setMessages((m) => [...m, userMsg])
    setDraft('')
    setError('')
    setSending(true)
    try {
      // Page context: lets the concierge resolve "this", "in pink?", or "the second one".
      const page: PageContext = {
        path: pathname,
        product_id: viewingProductId,
        category_filter: pathname === '/products' ? new URLSearchParams(search).get('category') : null,
        // Only results the shopper can actually see (the grid is hidden on login, sign-up, and cart).
        results_heading: resultsHiddenHere ? null : (chatResults.results?.heading ?? null),
        result_product_ids: resultsHiddenHere ? [] : (chatResults.results?.products.map((p) => p.product_id) ?? []),
      }
      setLive({ status: '', draft: '' })
      const onUpdate = (u: StreamUpdate) =>
        setLive((l) =>
          u.type === 'status' ? { ...l, status: u.text }
          : u.type === 'delta' ? { ...l, draft: u.reply }
          : { status: 'Double-checking that answer…', draft: '' }, // reset
        )
      const cartLines = cart.items.map(({ product_id, size, quantity }) => ({ product_id, size, quantity }))
      const reply = await sendChatMessage(text, history, page, cartLines, onUpdate)
      applyCartActions(reply.cart_actions)
      setMessages((m) => [
        ...m,
        {
          id: newId(),
          role: 'assistant',
          content: reply.reply,
          products: reply.products,
          resultsHeading: reply.results_heading,
          cartActions: reply.cart_actions,
        },
      ])
      chatResults.show(reply.results_heading, text, reply.products) // update the page with the matches
    } catch (err) {
      setError((err as Error).message)
      setDraft(text) // give the message back so they can retry
      setMessages((m) => m.filter((x) => x.id !== userMsg.id))
    } finally {
      setLive({ status: '', draft: '' })
      setSending(false)
      inputRef.current?.focus()
    }
  }

  const lastWithProducts = [...messages].reverse().find((m) => m.products && m.products.length > 0)

  return (
    <div className="chat-root">
      {open && (
        <section className="chat-panel" role="dialog" aria-label="Chat with Campus Customs" aria-modal="false">
          <header className="chat-header">
            <span className="chat-mark" aria-hidden="true">✦</span>
            <div className="chat-header-text">
              <p className="chat-title">Bulldog Blue Concierge</p>
              <p className="chat-sub">
                {user ? `Signed in as ${user.first_name} · conversation saved` : 'Ask about sizes, prices, and stock'}
              </p>
            </div>
            <button className="chat-close" onClick={() => setOpen(false)} aria-label="Close chat">×</button>
          </header>

          <div className="chat-messages" ref={listRef} aria-live="polite">
            {messages.map((m) => (
              <div key={m.id} className={`chat-msg ${m.role}`}>
                {m.role === 'assistant' ? <ChatText text={m.content} /> : <p>{m.content}</p>}
                {m.cartActions && m.cartActions.length > 0 && (
                  <div className="chat-cart-note" role="status">
                    {m.cartActions.map((a, i) => (
                      <p key={i}>
                        {a.action === 'add' ? '✓ Added to cart: ' : '✓ Removed from cart: '}
                        <strong>{a.quantity} × {a.name}</strong> ({a.size})
                      </p>
                    ))}
                    <Link to="/cart" className="chat-view-btn">View cart →</Link>
                  </div>
                )}
                {m.products && m.products.length > 0 && (
                  <div className="chat-products">
                    <div className="chat-thumbs">
                      {m.products.slice(0, 4).map((p) => (
                        <Link key={p.product_id} to={`/products/${p.product_id}`} className="chat-thumb" title={`${p.name}, ${formatPrice(p.price)}`}>
                          <img src={p.image_url} alt={p.name} />
                        </Link>
                      ))}
                      {m.products.length > 4 && <span className="chat-thumb-more">+{m.products.length - 4}</span>}
                    </div>
                    {chatResults.results && m === lastWithProducts && !resultsHiddenHere ? (
                      <button type="button" className="chat-view-btn" onClick={viewOnPage}>
                        {m.products.length === 1 ? 'Shown on the page' : `${m.products.length} pieces shown on the page`} ↓
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="chat-view-btn"
                        onClick={() => chatResults.show(m.resultsHeading ?? null, 'your earlier question', m.products ?? [])}
                        disabled={resultsHiddenHere}
                      >
                        Show {m.products.length === 1 ? 'it' : `all ${m.products.length}`} on the page
                      </button>
                    )}
                  </div>
                )}
              </div>
            ))}
            {sending && (live.draft ? (
              // The reply as it streams in. Shown lighter until the final, checked version replaces it.
              <div className="chat-msg assistant draft" aria-busy="true">
                <ChatText text={live.draft} />
                <p className="chat-status">{live.status && !live.status.startsWith('Double') ? 'Writing…' : live.status || 'Writing…'}</p>
              </div>
            ) : (
              <div className="chat-msg assistant typing-row" role="status" aria-label={live.status || 'Concierge is typing'}>
                <span className="typing"><span /><span /><span /></span>
                {live.status && <span className="chat-status">{live.status}</span>}
              </div>
            ))}
            {error && <p className="chat-error" role="alert">{error}</p>}
          </div>

          {!user && (
            <p className="chat-guest-note">Guest chats aren't saved. Log in to keep your conversation.</p>
          )}
          <form className="chat-input" onSubmit={send}>
            <label htmlFor="chat-text" className="sr-only">Message</label>
            <textarea
              id="chat-text"
              ref={inputRef}
              rows={1}
              maxLength={1000}
              placeholder={viewingProductId ? 'Ask about this item…' : 'Ask about our merch…'}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) send(e)
              }}
            />
            <button type="submit" className="btn btn-primary" disabled={!draft.trim() || sending}>
              {sending ? '…' : 'Send'}
            </button>
          </form>
        </section>
      )}

      <button
        className="chat-launcher"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-label={open ? 'Close chat' : 'Open chat'}
      >
        {open ? '×' : (
          <svg viewBox="0 0 24 24" width="26" height="26" aria-hidden="true">
            <path fill="currentColor" d="M4 4h16a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H8l-4 4V6a2 2 0 0 1 2-2Z" />
          </svg>
        )}
      </button>
    </div>
  )
}
