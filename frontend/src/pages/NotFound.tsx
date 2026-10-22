import { Link } from 'react-router-dom'

export default function NotFound() {
  return (
    <div className="page center">
      <h1>Page Not Found</h1>
      <p className="muted">That page seems to have wandered off.</p>
      <Link to="/" className="btn btn-primary">Back to Home</Link>
    </div>
  )
}
