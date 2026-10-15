import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, downloadTicket } from '../api.js'
import TripSummary from '../components/TripSummary.jsx'
import { formatPrice } from '../utils.js'

export default function MyBookings() {
  const [bookings, setBookings] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api('/api/bookings').then(setBookings).catch((err) => setError(err.message))
  }, [])

  return (
    <section>
      <h1>My bookings</h1>
      {error && <p className="error">{error}</p>}
      {bookings?.length === 0 && <p className="muted">No bookings yet. <Link to="/">Book a trip</Link></p>}
      {bookings?.map((b) => (
        <div key={b.id} className="card result">
          <TripSummary trip={b} />
          <div className="result-action">
            <span className={`badge ${b.status === 'CONFIRMED' ? 'badge-ok' : 'badge-warn'}`}>{b.status.replace('_', ' ')}</span>
            <div className="muted">PNR {b.pnr} · {formatPrice(b.amount)}</div>
            {b.status === 'CONFIRMED' ? (
              <button className="btn" onClick={() => downloadTicket(b).catch((err) => setError(err.message))}>Ticket PDF</button>
            ) : (
              <Link className="btn" to={`/pay/${b.id}`}>Pay now</Link>
            )}
          </div>
        </div>
      ))}
    </section>
  )
}
