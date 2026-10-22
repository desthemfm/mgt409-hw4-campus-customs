import { Link } from 'react-router-dom'
import { fetchProducts, type ProductSummary } from '../api'
import Countdown from '../components/Countdown'
import GameDayKit from '../components/GameDayKit'
import ProductCard from '../components/ProductCard'
import { ErrorMessage, Loading } from '../components/StatusMessage'
import { CATEGORY_TILES, FALL_PICK_IDS, PRIDE_PICK_IDS, productImage } from '../data/featured'
import { GAME_DAY, STANDS_IDS, gamePhase } from '../gameDay'
import { useAsync } from '../useAsync'

function pick(all: ProductSummary[] | null, ids: string[]) {
  if (!all) return []
  const byId = new Map(all.map((p) => [p.product_id, p]))
  return ids.map((id) => byId.get(id)).filter((p): p is ProductSummary => Boolean(p))
}

function ProductRow({ ids, state }: { ids: string[]; state: ReturnType<typeof useAsync<ProductSummary[]>> }) {
  if (state.loading) return <Loading />
  if (state.error) return <ErrorMessage message={state.error} />
  return (
    <div className="product-grid">
      {pick(state.data, ids).map((p) => <ProductCard key={p.product_id} product={p} sticker />)}
    </div>
  )
}

const TICKER = ['Boola Boola', 'Beat Harvard', 'Bulldogs', 'New Haven · Est. 1701', 'Officially licensed', 'Ask the Concierge']

const kickoffText = GAME_DAY.kickoff.toLocaleString('en-US', {
  weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZone: 'America/New_York',
})

export default function Home() {
  const products = useAsync((signal) => fetchProducts({}, signal), [])
  // Use the API's image URLs (they carry a ?v= version tag, so re-cleaned photos never show stale).
  const imageFor = (id: string) => products.data?.find((p) => p.product_id === id)?.image_url ?? productImage(id)
  const phase = gamePhase()

  return (
    <>
      {/* ---------- Game Day hero: night game at the Bowl ---------- */}
      <section className="gd-hero">
        <span className="gd-lights left" aria-hidden="true" />
        <span className="gd-lights right" aria-hidden="true" />
        <p className="gd-kicker">Officially licensed · The Game · Yale vs Harvard</p>
        {phase === 'after' ? (
          <h1 className="gd-title">Bulldog blue,<br /><em>all season.</em></h1>
        ) : (
          <h1 className="gd-title">Beat <em>Harvard.</em></h1>
        )}
        {phase === 'countdown' && (
          <>
            <Countdown to={GAME_DAY.kickoff} />
            <p className="gd-when">Kickoff {kickoffText} ET</p>
          </>
        )}
        {phase === 'gameday' && <p className="gd-when big">It's Game Day. Boola boola.</p>}
        <div className="gd-ctas">
          <a href="#kit" className="btn btn-light">Gear up for The Game</a>
          <Link to="/products" className="btn btn-ghost">Shop all 102 pieces</Link>
        </div>
      </section>

      <div className="ticker" aria-hidden="true">
        <div>
          {[...TICKER, ...TICKER].map((t, i) => (
            <span key={i}>{t}<i>✦</i></span>
          ))}
        </div>
      </div>

      {/* ---------- The kit and more for the stands ---------- */}
      <section className="section gd-band" id="kit">
        <div className="gd-split">
          <div>
            <div className="section-head left">
              <h2>The Game-Day Kit</h2>
              <p>Three pieces for the stands. Pick a size and add them all at once.</p>
            </div>
            <GameDayKit />
          </div>
          <div>
            <div className="section-head left">
              <h2>More for the Stands</h2>
              <p>Football and Yale Bowl pieces, with live sizes.</p>
            </div>
            <ProductRow ids={STANDS_IDS} state={products} />
          </div>
        </div>
      </section>

      {/* ---------- The store's own sections (wording from yalebulldogblue.com) ---------- */}
      <section className="section shop-intro">
        <div className="section-head">
          <h2>Shop Bulldog Blue</h2>
          <p>
            Casual comfort, classic Bulldog pride. One does not so much buy Yale blue as inherit it, and we
            are simply here to see that it is properly fitted.
          </p>
        </div>
        <div className="section-head">
          <h2 className="h-small">Yale Pride on the Go!</h2>
          <p>For the regatta, the Game, and the long weekend at the Cape: the pieces one reaches for without a second thought.</p>
        </div>
        <ProductRow ids={PRIDE_PICK_IDS} state={products} />
        <div className="center">
          <Link to="/products" className="btn btn-primary">Shop All</Link>
        </div>
      </section>

      <section className="section section-alt">
        <div className="section-head">
          <h2>Shop by Category</h2>
          <p>Everything in its proper place, as Mother always insisted.</p>
        </div>
        <div className="category-grid">
          {CATEGORY_TILES.map((c) => (
            <Link key={c.name} to={`/products?category=${encodeURIComponent(c.name)}`} className="category-tile">
              <img src={imageFor(c.productId)} alt="" />
              <span>{c.name}</span>
            </Link>
          ))}
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Cozy Up for Fall</h2>
          <p>
            When the elms along Hillhouse turn and there's a chill coming off the Sound, a good quarter-zip
            is less a garment than a quiet statement of good judgment.
          </p>
        </div>
        <ProductRow ids={FALL_PICK_IDS} state={products} />
        <div className="center">
          <Link to="/products" className="btn btn-outline">Shop Comfy Layers</Link>
        </div>
      </section>

      <section className="visit">
        <div className="visit-inner">
          <h2>Come Visit Us!</h2>
          <p>
            Our shop has stood just across from campus since 1975, long enough to have outfitted
            several generations of the same families. Do stop in after lunch at Mory's.
          </p>
          <address>57 Broadway<br />New Haven, CT 06511</address>
        </div>
      </section>
    </>
  )
}
