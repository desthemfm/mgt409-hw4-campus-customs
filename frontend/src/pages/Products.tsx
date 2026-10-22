import { useSearchParams } from 'react-router-dom'
import { fetchCategories, fetchProducts } from '../api'
import ProductCard from '../components/ProductCard'
import { ErrorMessage, Loading } from '../components/StatusMessage'
import { SIZES, getPreferredSize, setPreferredSize } from '../sizePreference'
import { useAsync } from '../useAsync'

const ALL = 'All'

export default function Products() {
  const [params, setParams] = useSearchParams()
  const active = params.get('category') ?? ALL
  const sizeParam = params.get('size')
  const size = sizeParam && (SIZES as readonly string[]).includes(sizeParam) ? sizeParam : null
  const remembered = getPreferredSize()

  const categories = useAsync((signal) => fetchCategories(signal), [])
  const products = useAsync(
    (signal) => fetchProducts(active === ALL ? {} : { category: active }, signal),
    [active],
  )
  const total = categories.data?.reduce((sum, c) => sum + c.count, 0)

  // Keep the category and size filters together in the URL (shareable, and the Back button works).
  function update(next: { category?: string; size?: string | null }) {
    const category = next.category ?? active
    const nextSize = next.size === undefined ? size : next.size
    const q: Record<string, string> = {}
    if (category !== ALL) q.category = category
    if (nextSize) q.size = nextSize
    setParams(q)
  }

  function chooseSize(s: string | null) {
    setPreferredSize(s) // remembered for next time, and preselected on product pages
    update({ size: s })
  }

  const shown = products.data && size ? products.data.filter((p) => p.sizes_in_stock.includes(size)) : products.data

  return (
    <div className="page">
      <header className="page-head">
        <p className="eyebrow">The Collection</p>
        <h1>Products</h1>
        <p className="lede">Officially licensed Yale apparel, sorted for your convenience.</p>
      </header>

      {categories.data && (
        <div className="chips" role="group" aria-label="Filter by category">
          {[{ name: ALL, count: total ?? 0 }, ...categories.data].map((c) => (
            <button
              key={c.name}
              className={c.name === active ? 'chip active' : 'chip'}
              aria-pressed={c.name === active}
              onClick={() => update({ category: c.name })}
            >
              {c.name} <span className="chip-count">{c.count}</span>
            </button>
          ))}
        </div>
      )}

      {/* Shop your size: show only pieces in stock in the shopper's size */}
      <div className="size-filter" role="group" aria-label="Shop your size: show only pieces in stock in this size">
        <span className="size-filter-label">Your size</span>
        <button type="button" className={!size ? 'chip active' : 'chip'} aria-pressed={!size} onClick={() => chooseSize(null)}>
          Any
        </button>
        {SIZES.map((s) => (
          <button key={s} type="button" className={s === size ? 'chip active' : 'chip'} aria-pressed={s === size} onClick={() => chooseSize(s)}>
            {s}
          </button>
        ))}
        {!size && remembered && (
          <button type="button" className="link-btn strong" onClick={() => chooseSize(remembered)}>
            Show only my size ({remembered})
          </button>
        )}
      </div>

      {products.loading && <Loading label="Fetching the collection…" />}
      {products.error && <ErrorMessage message={products.error} />}
      {shown && products.data && !products.loading && (
        <>
          <p className="result-count" role="status">
            {size
              ? `${shown.length} of ${products.data.length} ${products.data.length === 1 ? 'piece' : 'pieces'} in stock in ${size}`
              : `${shown.length} ${shown.length === 1 ? 'piece' : 'pieces'}`}
          </p>
          {shown.length > 0 ? (
            <div className="product-grid">
              {shown.map((p) => <ProductCard key={p.product_id} product={p} showInfo highlightSize={size} />)}
            </div>
          ) : (
            <p className="muted">
              {size ? `Nothing in this category is in stock in ${size} right now.` : 'Nothing in this category at the moment.'}
            </p>
          )}
        </>
      )}
    </div>
  )
}
