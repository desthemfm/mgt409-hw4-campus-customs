import { useSearchParams } from 'react-router-dom'
import { fetchCategories, fetchProducts } from '../api'
import ProductCard from '../components/ProductCard'
import { ErrorMessage, Loading } from '../components/StatusMessage'
import { useAsync } from '../useAsync'

const ALL = 'All'

export default function Products() {
  const [params, setParams] = useSearchParams()
  const active = params.get('category') ?? ALL

  const categories = useAsync((signal) => fetchCategories(signal), [])
  const products = useAsync(
    (signal) => fetchProducts(active === ALL ? {} : { category: active }, signal),
    [active],
  )
  const total = categories.data?.reduce((sum, c) => sum + c.count, 0)

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
              onClick={() => setParams(c.name === ALL ? {} : { category: c.name })}
            >
              {c.name} <span className="chip-count">{c.count}</span>
            </button>
          ))}
        </div>
      )}

      {products.loading && <Loading label="Fetching the collection…" />}
      {products.error && <ErrorMessage message={products.error} />}
      {products.data && !products.loading && (
        <>
          <p className="result-count">
            {products.data.length} {products.data.length === 1 ? 'piece' : 'pieces'}
          </p>
          {products.data.length > 0 ? (
            <div className="product-grid">
              {products.data.map((p) => <ProductCard key={p.product_id} product={p} showInfo />)}
            </div>
          ) : (
            <p className="muted">Nothing in this category at the moment.</p>
          )}
        </>
      )}
    </div>
  )
}
