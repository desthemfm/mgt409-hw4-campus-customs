import { useState } from 'react'
import { Link, NavLink, useNavigate } from 'react-router-dom'
import { useCart } from '../cart'
import { useAuth } from '../auth'

const PAGE_LINKS = [
  { to: '/', label: 'Home' },
  { to: '/products', label: 'Products' },
  { to: '/about', label: 'About Us' },
]

const GUEST_LINKS = [
  { to: '/login', label: 'Log In' },
  { to: '/create-account', label: 'Create Account' },
]

export default function NavBar() {
  const [open, setOpen] = useState(false)
  const { count } = useCart()
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const links = user ? PAGE_LINKS : [...PAGE_LINKS, ...GUEST_LINKS]

  async function handleLogout() {
    setOpen(false)
    await logout()
    navigate('/')
  }

  return (
    <header className="site-header">
      <div className="header-inner">
        <Link to="/" className="brand" onClick={() => setOpen(false)}>
          <span className="brand-mark" aria-hidden="true">Y</span>
          <span className="brand-text">
            <span className="brand-name">Yale Bulldog Blue</span>
            <span className="brand-sub">by Campus Customs</span>
          </span>
        </Link>

        <div className="header-actions">
          <NavLink
            to="/cart"
            className={({ isActive }) => (isActive ? 'cart-button active' : 'cart-button')}
            aria-label={`Cart, ${count} ${count === 1 ? 'item' : 'items'}`}
            onClick={() => setOpen(false)}
          >
            <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
              <path fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
                d="M6 7h12l-1 13H7L6 7Zm3 0V5a3 3 0 0 1 6 0v2" />
            </svg>
            <span className="cart-label">Cart</span>
            {count > 0 && <span className="cart-count" aria-hidden="true">{count}</span>}
          </NavLink>

          <button
            className="menu-toggle"
            aria-expanded={open}
            aria-controls="primary-nav"
            onClick={() => setOpen((o) => !o)}
          >
            {open ? 'Close' : 'Menu'}
          </button>
        </div>

        <nav id="primary-nav" aria-label="Main" className={open ? 'nav open' : 'nav'}>
          <ul>
            {links.map((link) => (
              <li key={link.to}>
                <NavLink
                  to={link.to}
                  end={link.to === '/'}
                  className={({ isActive }) =>
                    [link.to === '/create-account' ? 'nav-cta' : '', isActive ? 'active' : ''].join(' ')
                  }
                  onClick={() => setOpen(false)}
                >
                  {link.label}
                </NavLink>
              </li>
            ))}
            {user && (
              <>
                <li className="nav-greeting" aria-label={`Signed in as ${user.name}`}>Hi, {user.first_name}</li>
                <li>
                  <button type="button" className="nav-logout" onClick={handleLogout}>Log Out</button>
                </li>
              </>
            )}
          </ul>
        </nav>
      </div>
    </header>
  )
}
