import { Link, useLocation, useNavigate } from 'react-router-dom'
import { clearSession, getUser } from '../api.js'

export default function NavBar() {
  useLocation() // re-render on navigation so sign-in/out state is current
  const navigate = useNavigate()
  const user = getUser()

  function signOut() {
    clearSession()
    navigate('/signin')
  }

  return (
    <header className="navbar">
      <Link to="/" className="brand">✈ QuickBook</Link>
      {user && (
        <nav>
          <Link to="/bookings">My bookings</Link>
          <span className="muted">Hi, {user.full_name.split(' ')[0]}</span>
          <button className="btn btn-ghost" onClick={signOut}>Sign out</button>
        </nav>
      )}
    </header>
  )
}
