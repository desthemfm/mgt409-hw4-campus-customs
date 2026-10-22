import { useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchProduct, formatPrice, type ProductDetail } from '../api'
import { useCart } from '../cart'
import { KIT_IDS } from '../gameDay'
import { useAsync } from '../useAsync'
import { ErrorMessage, Loading } from './StatusMessage'

const SIZES = ['XS', 'S', 'M', 'L', 'XL', 'XXL']

// The game-day kit: three pieces, one size, one click. Uses live stock and says plainly
// if a piece is sold out in the chosen size (it is skipped, never oversold).
export default function GameDayKit() {
  const kit = useAsync((signal) => Promise.all(KIT_IDS.map((id) => fetchProduct(id, signal))), [])
  const cart = useCart()
  const [size, setSize] = useState('M')
  const [note, setNote] = useState('')

  if (kit.loading) return <Loading label="Laying out the kit…" />
  if (kit.error || !kit.data) return <ErrorMessage message={kit.error ?? 'Could not load the kit.'} />

  const stockIn = (p: ProductDetail) => p.inventory.find((s) => s.size === size)?.quantity ?? 0
  const available = kit.data.filter((p) => stockIn(p) > 0)
  const total = kit.data.reduce((t, p) => t + p.price, 0)

  function addKit() {
    const added: string[] = []
    const skipped: string[] = []
    for (const p of kit.data ?? []) {
      const n = cart.add(
        { product_id: p.product_id, size, name: p.name, price: p.price, image_url: p.image_url },
        1,
        stockIn(p),
      )
      ;(n ? added : skipped).push(p.name)
    }
    setNote(
      added.length === 0
        ? `None of the kit is available in ${size} right now. Try another size.`
        : `Added ${added.length} of 3 in ${size}.` + (skipped.length ? ` Not added (sold out in ${size}, or already in your cart): ${skipped.join(', ')}.` : ''),
    )
  }

  return (
    <div className="kit">
      <div className="kit-items">
        {kit.data.map((p) => {
          const left = stockIn(p)
          return (
            <Link to={`/products/${p.product_id}`} className="kit-item" key={p.product_id}>
              <img src={p.image_url} alt={p.name} />
              <span className="kit-name">{p.name}</span>
              <span className="kit-price">{formatPrice(p.price)}</span>
              <span className={left === 0 ? 'kit-stock out' : left <= 5 ? 'kit-stock low' : 'kit-stock'}>
                {left === 0 ? `Sold out in ${size}` : left <= 5 ? `Only ${left} left in ${size}` : `In stock in ${size}`}
              </span>
            </Link>
          )
        })}
      </div>

      <div className="kit-foot">
        <div>
          <span className="kit-total">{formatPrice(total)}</span>
          <span className="kit-total-note">The three current prices added up</span>
        </div>
        <div className="kit-actions">
          <label htmlFor="kit-size" className="sr-only">Size for the kit</label>
          <select id="kit-size" value={size} onChange={(e) => { setSize(e.target.value); setNote('') }}>
            {SIZES.map((s) => <option key={s}>{s}</option>)}
          </select>
          <button type="button" className="btn btn-accent" onClick={addKit} disabled={available.length === 0}>
            Add the kit in {size}
          </button>
        </div>
      </div>
      {note && <p className="kit-note" role="status">{note} <Link to="/cart">View cart →</Link></p>}
    </div>
  )
}
