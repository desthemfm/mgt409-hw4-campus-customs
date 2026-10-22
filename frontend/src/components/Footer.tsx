import { Link } from 'react-router-dom'

const YEAR = new Date().getFullYear()

export default function Footer() {
  return (
    <footer className="site-footer">
      <div className="footer-inner">
        <div>
          <p className="footer-brand">Yale Bulldog Blue by Campus Customs</p>
          <p>57 Broadway, New Haven, CT 06511</p>
          <p className="muted">Serving Yale since 1975</p>
        </div>
        <nav aria-label="Footer">
          <ul>
            <li><Link to="/products">Shop All</Link></li>
            <li><Link to="/about">About Us</Link></li>
            <li><Link to="/login">Log In</Link></li>
            <li><Link to="/create-account">Create Account</Link></li>
          </ul>
        </nav>
      </div>
      <p className="copyright">© {YEAR} Yale Bulldog Blue by Campus Customs · Officially Licensed Merchandise</p>
    </footer>
  )
}
