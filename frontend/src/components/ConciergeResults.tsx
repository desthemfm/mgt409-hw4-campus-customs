import { useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { useChatResults } from '../chatResults'
import ProductCard from './ProductCard'

// Pages where a results grid would get in the way of a form.
const HIDDEN_ON = ['/login', '/create-account', '/cart']
const isProductPage = (path: string) => /^\/products\/[^/]+$/.test(path)

// The on-page product grid that the chat concierge updates. It appears at the top of the
// page whenever the agent's reply includes matching items.
//
// On a single-item page (/products/:id) it folds down to one slim bar, so the item page
// from Problem 3 stays at the top exactly as before. The shopper can reopen the grid, and
// new results from the chat open it automatically.
export default function ConciergeResults() {
  const { results, clear } = useChatResults()
  const { pathname } = useLocation()
  const ref = useRef<HTMLElement>(null)
  const hidden = HIDDEN_ON.includes(pathname)
  const onProductPage = isProductPage(pathname)
  const [expandedOnProductPage, setExpandedOnProductPage] = useState(false)

  // Opening a product (from any card) folds the grid away.
  useEffect(() => {
    setExpandedOnProductPage(false)
  }, [pathname])

  // New results from the chat: show them in full and bring them into view.
  useEffect(() => {
    if (!results || hidden) return
    setExpandedOnProductPage(true)
    ref.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [results?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!results || hidden) return null

  const n = results.products.length
  const pieces = `${n} ${n === 1 ? 'piece' : 'pieces'}`
  const collapsed = onProductPage && !expandedOnProductPage

  if (collapsed) {
    return (
      <section ref={ref} id="concierge-results" className="concierge-bar" aria-label="Concierge results">
        <div className="concierge-bar-inner">
          <p>
            <span className="eyebrow">From your concierge</span>
            <strong>{results.heading}</strong> <span className="muted">· {pieces}</span>
          </p>
          <div className="concierge-bar-actions">
            <button type="button" className="link-btn strong" onClick={() => setExpandedOnProductPage(true)} aria-expanded={false} aria-controls="concierge-results">
              View results
            </button>
            <button type="button" className="link-btn" onClick={clear}>Clear</button>
          </div>
        </div>
      </section>
    )
  }

  return (
    <section ref={ref} id="concierge-results" className="concierge-results" aria-labelledby="concierge-results-title" tabIndex={-1}>
      <div className="concierge-results-inner">
        <div className="concierge-results-head">
          <div>
            <p className="eyebrow">From your concierge</p>
            <h2 id="concierge-results-title">{results.heading}</h2>
            <p className="muted concierge-question">
              {pieces} for “{results.question}”
            </p>
          </div>
          <div className="concierge-head-actions">
            {onProductPage && (
              <button type="button" className="btn btn-outline btn-small" onClick={() => setExpandedOnProductPage(false)} aria-expanded={true}>
                Hide results
              </button>
            )}
            <button type="button" className="btn btn-outline btn-small" onClick={clear}>
              Clear results
            </button>
          </div>
        </div>
        <p className="sr-only" aria-live="polite">
          {`Showing ${pieces}: ${results.heading}`}
        </p>
        <div className="product-grid" key={results.id}>
          {results.products.map((p) => <ProductCard key={p.product_id} product={p} showInfo sticker />)}
        </div>
      </div>
    </section>
  )
}
