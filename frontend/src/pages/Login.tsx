import { useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'
import PasswordInput from '../components/PasswordInput'

export default function Login() {
  const { user, login, logout } = useAuth()
  const navigate = useNavigate()
  const from = (useLocation().state as { from?: string } | null)?.from ?? '/'
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const data = new FormData(e.currentTarget)
    const email = String(data.get('email') ?? '').trim()
    const password = String(data.get('password') ?? '')
    if (!email || !password) {
      setError('Please enter your email and password.')
      return
    }
    setError('')
    setBusy(true)
    try {
      await login(email, password)
      navigate(from, { replace: true })
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  if (user) {
    return (
      <div className="page auth">
        <div className="auth-card center-text">
          <h1>Welcome back, {user.first_name}.</h1>
          <p className="muted">You're signed in as {user.email}.</p>
          <Link to="/products" className="btn btn-primary btn-block">Continue Shopping</Link>
          <button type="button" className="link-btn spaced" onClick={logout}>Not you? Log out</button>
        </div>
      </div>
    )
  }

  return (
    <div className="page auth">
      <div className="auth-card">
        <h1>Log In</h1>
        <p className="muted">Welcome back. Do come in.</p>
        <form onSubmit={handleSubmit} noValidate>
          <label htmlFor="email">Email</label>
          <input id="email" name="email" type="email" autoComplete="email" required />
          <label htmlFor="password">Password</label>
          <PasswordInput id="password" name="password" autoComplete="current-password" required />
          {error && <p className="form-error" role="alert">{error}</p>}
          <button type="submit" className="btn btn-primary btn-block" disabled={busy}>
            {busy ? 'Logging in…' : 'Log In'}
          </button>
        </form>
        <p className="auth-switch">New to Bulldog Blue? <Link to="/create-account" state={{ from }}>Create an account</Link></p>
      </div>
    </div>
  )
}
