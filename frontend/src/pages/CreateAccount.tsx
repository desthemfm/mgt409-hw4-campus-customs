import { useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'
import PasswordInput from '../components/PasswordInput'

const MIN_LENGTH = 8

// Quick checks in the browser for instant feedback. The backend repeats every check
// (plus a common-password list), because browser checks can be bypassed.
function localProblem(f: Record<string, string>): string | null {
  if (!f.first_name || !f.last_name || !f.email || !f.password || !f.confirm_password) return 'Please fill in every field.'
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(f.email)) return 'Please enter a valid email address.'
  if (f.password.length < MIN_LENGTH) return `Your password must be at least ${MIN_LENGTH} characters.`
  if (f.password !== f.confirm_password) return 'The passwords do not match.'
  return null
}

export default function CreateAccount() {
  const { user, signup } = useAuth()
  const navigate = useNavigate()
  const from = (useLocation().state as { from?: string } | null)?.from ?? '/'
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const data = new FormData(e.currentTarget)
    const get = (k: string) => String(data.get(k) ?? '')
    const fields = {
      first_name: get('first_name').trim(),
      last_name: get('last_name').trim(),
      email: get('email').trim(),
      password: get('password'),
      confirm_password: get('confirm_password'),
    }
    const problem = localProblem(fields)
    if (problem) {
      setError(problem)
      return
    }
    setError('')
    setBusy(true)
    try {
      await signup(fields)
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
          <h1>You're all set, {user.first_name}.</h1>
          <p className="muted">You're signed in as {user.email}.</p>
          <Link to="/products" className="btn btn-primary btn-block">Start Shopping</Link>
        </div>
      </div>
    )
  }

  return (
    <div className="page auth">
      <div className="auth-card">
        <h1>Create Account</h1>
        <p className="muted">Membership has its privileges, chiefly a personal shopper who never forgets your size.</p>
        <form onSubmit={handleSubmit} noValidate>
          <div className="field-row">
            <div>
              <label htmlFor="first_name">First name</label>
              <input id="first_name" name="first_name" autoComplete="given-name" maxLength={50} required />
            </div>
            <div>
              <label htmlFor="last_name">Last name</label>
              <input id="last_name" name="last_name" autoComplete="family-name" maxLength={50} required />
            </div>
          </div>
          <label htmlFor="email">Email</label>
          <input id="email" name="email" type="email" autoComplete="email" maxLength={254} required />
          <label htmlFor="password">Password</label>
          <PasswordInput
            id="password"
            name="password"
            autoComplete="new-password"
            minLength={MIN_LENGTH}
            maxLength={128}
            required
            aria-describedby="pw-hint"
          />
          <p id="pw-hint" className="hint">
            At least {MIN_LENGTH} characters. A short phrase you'll remember is stronger than a jumble of symbols.
          </p>
          <label htmlFor="confirm_password">Confirm password</label>
          <PasswordInput id="confirm_password" name="confirm_password" autoComplete="new-password" maxLength={128} required />
          {error && <p className="form-error" role="alert">{error}</p>}
          <button type="submit" className="btn btn-primary btn-block" disabled={busy}>
            {busy ? 'Creating your account…' : 'Create Account'}
          </button>
        </form>
        <p className="auth-switch">Already a member? <Link to="/login" state={{ from }}>Log in</Link></p>
      </div>
    </div>
  )
}
