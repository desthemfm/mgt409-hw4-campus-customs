import { Link } from 'react-router-dom'
import { formatPrice, type ProductSummary } from '../api'

const ALL_SIZES = 6

function sizeLine(p: ProductSummary) {
  if (!p.in_stock) return 'Sold out'
  if (p.sizes_in_stock.length === ALL_SIZES) return 'All sizes in stock'
  return `In stock: ${p.sizes_in_stock.join(', ')}`
}

// One product tile: image, name, price, and (optionally) a short line of info plus sizes.
// Scarce enough to call out in a busy grid: the last one or two of a size.
const lastFew = (note: string | null) => Boolean(note && /^Only [12] left/.test(note))

export default function ProductCard({
  product,
  showInfo = false,
  sticker = false,
}: {
  product: ProductSummary
  showInfo?: boolean
  sticker?: boolean // bold sticker for the last 1-2 of a size (used on hand-picked rows); real stock only
}) {
  return (
    <Link to={`/products/${product.product_id}`} className="product-card">
      <div className="product-image">
        <img src={product.image_url} alt={product.name} loading="lazy" />
        {!product.in_stock && <span className="badge badge-out">Sold out</span>}
        {sticker && product.in_stock && lastFew(product.low_stock_note) && <span className="badge badge-low">{product.low_stock_note}</span>}
      </div>
      <h3>{product.name}</h3>
      <p className="price">{formatPrice(product.price)}</p>
      {showInfo && (
        <>
          <p className="card-desc">{product.short_info}</p>
          <p className={product.in_stock ? 'card-sizes' : 'card-sizes out'}>{sizeLine(product)}</p>
          {!sticker && lastFew(product.low_stock_note) && <p className="card-low">{product.low_stock_note}</p>}
        </>
      )}
    </Link>
  )
}
