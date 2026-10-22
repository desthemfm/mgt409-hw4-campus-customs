import { Link } from 'react-router-dom'
import { fetchProduct, formatPrice, type ProductDetail } from '../api'
import { useCart, type CartItem } from '../cart'
import { ErrorMessage, Loading } from '../components/StatusMessage'
import { useAsync } from '../useAsync'

// Re-check every product in the cart against the live database, so price and stock are never stale.
async function loadLive(ids: string[], signal: AbortSignal) {
  const products = await Promise.all(ids.map((id) => fetchProduct(id, signal).catch(() => null)))
  return new Map(ids.map((id, i) => [id, products[i]]))
}

function CartLine({ item, live }: { item: CartItem; live: ProductDetail | null | undefined }) {
  const cart = useCart()
  const stock = live?.inventory.find((s) => s.size === item.size)?.quantity ?? 0
  const price = live?.price ?? item.price
  const tooMany = live ? item.quantity > stock : false

  return (
    <li className="cart-line">
      <Link to={`/products/${item.product_id}`} className="cart-thumb">
        <img src={item.image_url} alt={item.name} />
      </Link>
      <div className="cart-line-info">
        <Link to={`/products/${item.product_id}`} className="cart-line-name">{item.name}</Link>
        <p className="muted">Size {item.size} · {formatPrice(price)} each</p>
        {live === null && <p className="line-warn">This item is no longer in the catalogue.</p>}
        {live && price !== item.price && (
          <p className="line-warn">Price is now {formatPrice(price)} (was {formatPrice(item.price)} when added).</p>
        )}
        {tooMany && (
          <p className="line-warn">
            {stock === 0 ? `Size ${item.size} has sold out.` : `Only ${stock} left in size ${item.size}. Please lower the quantity.`}
          </p>
        )}
      </div>
      <div className="qty-stepper small">
        <button
          type="button"
          onClick={() => cart.setQuantity(item.product_id, item.size, item.quantity - 1)}
          aria-label={`Decrease quantity of ${item.name}`}
        >
          −
        </button>
        <span aria-live="polite" aria-label={`Quantity ${item.quantity}`}>{item.quantity}</span>
        <button
          type="button"
          onClick={() => cart.setQuantity(item.product_id, item.size, item.quantity + 1)}
          disabled={!live || item.quantity >= stock}
          aria-label={`Increase quantity of ${item.name}`}
        >
          +
        </button>
      </div>
      <p className="cart-line-total">{formatPrice(price * item.quantity)}</p>
      <button type="button" className="link-btn" onClick={() => cart.remove(item.product_id, item.size)}>
        Remove
      </button>
    </li>
  )
}

export default function Cart() {
  const cart = useCart()
  const ids = [...new Set(cart.items.map((i) => i.product_id))]
  const live = useAsync((signal) => loadLive(ids, signal), [ids.join(',')])

  if (cart.items.length === 0) {
    return (
      <div className="page center">
        <h1>Your Cart</h1>
        <p className="muted">Your cart is empty. A rare moment of restraint.</p>
        <Link to="/products" className="btn btn-primary">Shop Bulldog Blue</Link>
      </div>
    )
  }

  const priceOf = (i: CartItem) => live.data?.get(i.product_id)?.price ?? i.price
  const subtotal = cart.items.reduce((sum, i) => sum + priceOf(i) * i.quantity, 0)
  const hasProblems = cart.items.some((i) => {
    const p = live.data?.get(i.product_id)
    return p === null || (p && i.quantity > (p.inventory.find((s) => s.size === i.size)?.quantity ?? 0))
  })

  return (
    <div className="page">
      <header className="page-head">
        <h1>Your Cart</h1>
        <p className="muted">{cart.count} {cart.count === 1 ? 'item' : 'items'}</p>
      </header>

      {live.loading && <Loading label="Checking current prices and stock…" />}
      {live.error && <ErrorMessage message={live.error} />}

      <div className="cart-layout">
        <ul className="cart-lines">
          {cart.items.map((item) => (
            <CartLine key={`${item.product_id}-${item.size}`} item={item} live={live.data?.get(item.product_id)} />
          ))}
        </ul>

        <aside className="cart-summary" aria-label="Order summary">
          <h2>Summary</h2>
          <dl>
            <dt>Subtotal</dt>
            <dd>{formatPrice(subtotal)}</dd>
            <dt>Shipping &amp; tax</dt>
            <dd>Calculated at checkout</dd>
          </dl>
          {hasProblems && <p className="line-warn">Please fix the items marked above.</p>}
          <button type="button" className="btn btn-primary btn-block" disabled>
            Checkout
          </button>
          <p className="hint">Online checkout isn't available on this site yet. Your cart is saved in this browser.</p>
          <button type="button" className="link-btn" onClick={cart.clear}>Empty cart</button>
        </aside>
      </div>
    </div>
  )
}
