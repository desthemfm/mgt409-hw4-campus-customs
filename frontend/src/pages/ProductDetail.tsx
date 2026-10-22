import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useCart } from '../cart'
import { fetchProduct, formatPrice, type SizeStock } from '../api'
import { ErrorMessage, Loading } from '../components/StatusMessage'
import { useAsync } from '../useAsync'

const LOW_STOCK = 5

function stockLabel(s: SizeStock) {
  if (s.quantity === 0) return 'Out of stock'
  if (s.quantity <= LOW_STOCK) return `Only ${s.quantity} left`
  return `${s.quantity} in stock`
}

export default function ProductDetail() {
  const { productId = '' } = useParams()
  const { data: product, error, loading } = useAsync((signal) => fetchProduct(productId, signal), [productId])
  const [picked, setPicked] = useState<string | null>(null)
  const [qty, setQty] = useState(1)
  const [addedNote, setAddedNote] = useState('')
  const cart = useCart()

  if (loading) return <div className="page"><Loading label="Fetching product…" /></div>
  if (error || !product) {
    return (
      <div className="page">
        <ErrorMessage message={error === 'Product not found' ? "We couldn't find that product." : error ?? 'Something went wrong.'} />
        <p><Link to="/products">← Back to all products</Link></p>
      </div>
    )
  }

  const selected = product.inventory.find((s) => s.size === picked) ?? null
  const inCart = selected ? cart.quantityOf(product.product_id, selected.size) : 0
  const canAdd = selected ? selected.quantity - inCart : 0

  function pickSize(size: string) {
    setPicked(size)
    setQty(1)
    setAddedNote('')
  }

  function addToCart() {
    if (!product || !selected) return
    const added = cart.add(
      { product_id: product.product_id, size: selected.size, name: product.name, price: product.price, image_url: product.image_url },
      qty,
      selected.quantity,
    )
    setQty(1)
    setAddedNote(
      added === qty
        ? `Added ${added} × ${product.name} (${selected.size}) to your cart.`
        : `Only ${added} more could be added. That's all we have in ${selected.size}.`,
    )
  }

  return (
    <div className="page">
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link to="/products">Products</Link>
        <span aria-hidden="true">/</span>
        <Link to={`/products?category=${encodeURIComponent(product.category)}`}>{product.category}</Link>
        <span aria-hidden="true">/</span>
        <span aria-current="page">{product.name}</span>
      </nav>

      <div className="detail">
        <div className="detail-image">
          <img src={product.image_url} alt={product.name} />
        </div>

        <div className="detail-info">
          <p className="eyebrow">{product.category}</p>
          <h1>{product.name}</h1>
          <p className="detail-price">{formatPrice(product.price)}</p>
          <p className={product.in_stock ? 'stock-line in' : 'stock-line out'}>
            {product.in_stock ? `In stock · ${product.total_stock} available across all sizes` : 'Currently sold out in every size'}
          </p>

          <p className="detail-desc">{product.description}</p>

          <fieldset className="sizes">
            <legend>Size</legend>
            <div className="size-grid">
              {product.inventory.map((s) => (
                <button
                  key={s.size}
                  type="button"
                  className={['size-btn', s.quantity === 0 ? 'unavailable' : '', picked === s.size ? 'picked' : ''].join(' ')}
                  aria-pressed={picked === s.size}
                  aria-label={`${s.size}: ${stockLabel(s)}`}
                  onClick={() => pickSize(s.size)}
                >
                  <span className="size-name">{s.size}</span>
                  <span className="size-qty">{s.quantity === 0 ? 'Sold out' : s.quantity <= LOW_STOCK ? `${s.quantity} left` : 'In stock'}</span>
                </button>
              ))}
            </div>
            <p className="size-status" aria-live="polite">
              {selected ? `Size ${selected.size}: ${stockLabel(selected)}` : 'Choose a size to see availability.'}
            </p>
          </fieldset>

          <div className="add-row">
            <label htmlFor="qty" className="sr-only">Quantity</label>
            <div className="qty-stepper">
              <button type="button" onClick={() => setQty((q) => Math.max(1, q - 1))} disabled={qty <= 1} aria-label="Decrease quantity">−</button>
              <input
                id="qty"
                type="number"
                min={1}
                max={Math.max(1, canAdd)}
                value={qty}
                onChange={(e) => setQty(Math.max(1, Math.min(Math.max(1, canAdd), Number(e.target.value) || 1)))}
              />
              <button type="button" onClick={() => setQty((q) => Math.min(canAdd, q + 1))} disabled={qty >= canAdd} aria-label="Increase quantity">+</button>
            </div>
            <button type="button" className="btn btn-primary add-btn" onClick={addToCart} disabled={!selected || canAdd <= 0}>
              {!selected ? 'Choose a size' : selected.quantity === 0 ? 'Sold out' : canAdd <= 0 ? 'All in your cart' : 'Add to Cart'}
            </button>
          </div>
          {inCart > 0 && !addedNote && (
            <p className="cart-note">You have {inCart} in size {selected?.size} in your cart.</p>
          )}
          {addedNote && (
            <p className="cart-note" role="status">
              {addedNote} <Link to="/cart">View cart →</Link>
            </p>
          )}


          <dl className="specs">
            <dt>Style</dt>
            <dd>{product.garment_type}</dd>
            {product.colors.length > 0 && (
              <>
                <dt>Colors on the item</dt>
                <dd>{product.colors.join(', ')}</dd>
              </>
            )}
            <dt>Item</dt>
            <dd>{product.product_id}</dd>
          </dl>
        </div>
      </div>
    </div>
  )
}
