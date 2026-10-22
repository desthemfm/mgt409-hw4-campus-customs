import { Link } from 'react-router-dom'

export default function About() {
  return (
    <div className="page about">
      <header className="page-head">
        <p className="eyebrow">Our Story</p>
        <h1>About Us</h1>
        <p className="lede">A family concern, a stone's throw from Old Campus, now in its sixth decade.</p>
      </header>

      <section className="prose">
        <h2>Since 1975</h2>
        <p>
          Campus Customs began in 1975, when our father opened a modest Yale memorabilia shop directly
          across from the University. Half a century on, we remain at that very address, which, in
          New Haven, is about as close to old money as a storefront can come.
        </p>
        <p>
          Father has since retired, as gentlemen eventually must. The business is now
          kept by his sons, Joel and Jeremy Cobden, who have been entrusted with its two family
          heirlooms: a genuine devotion to customer service and a firm sense of how business ought
          to be conducted.
        </p>

        <h2>What We Do</h2>
        <p>
          What began as pennants and sweatshirts has, over the years, grown into a full house of
          services, all handled under one roof beside the original shop:
        </p>
        <ul>
          <li>Screen printing and embroidery, from a single crest to a full reunion order</li>
          <li>Web store design and online fulfillment</li>
          <li>Graphic design</li>
          <li>Complete merchandise for events, galas, and the occasional regatta</li>
        </ul>
        <p>
          Keeping every step in-house means we can turn things around briskly, without anyone having
          to raise their voice.
        </p>

        <h2>Where to Find Us</h2>
        <p>
          Our flagship is at 57 Broadway in New Haven, with further shops in Branford, Connecticut, and
          Celebration, Florida, for those who winter in the South. And, of course, we're always open
          right here online.
        </p>

        <h2>Officially Licensed</h2>
        <p>
          Every Bulldog Blue piece is officially licensed. One simply doesn't wear an imitation crest.
        </p>
      </section>

      <div className="center">
        <Link to="/products" className="btn btn-primary">Shop Bulldog Blue</Link>
      </div>
    </div>
  )
}
