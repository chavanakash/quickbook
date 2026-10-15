import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, downloadTicket } from '../api.js'
import TripSummary from '../components/TripSummary.jsx'
import { formatPrice } from '../utils.js'

export default function Confirmation() {
  const { bookingId } = useParams()
  const [booking, setBooking] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api(`/api/bookings/${bookingId}`).then(setBooking).catch((err) => setError(err.message))
  }, [bookingId])

  if (!booking) return <section>{error ? <p className="error">{error}</p> : <p className="muted">Loading…</p>}</section>

  const confirmed = booking.status === 'CONFIRMED'

  return (
    <section>
      <div className="card confirmation">
        <h1>{confirmed ? '🎉 Booking confirmed!' : 'Payment pending'}</h1>
        <p>PNR <strong className="pnr">{booking.pnr}</strong></p>
        <TripSummary trip={booking} />
        <ul className="passenger-list">
          {booking.passengers.map((p, i) => <li key={i}>{p.name} ({p.age})</li>)}
        </ul>
        <p>Total paid: <strong>{formatPrice(booking.amount)}</strong></p>
        {error && <p className="error">{error}</p>}
        <div className="actions">
          {confirmed ? (
            <button className="btn" onClick={() => downloadTicket(booking).catch((err) => setError(err.message))}>
              Download ticket (PDF)
            </button>
          ) : (
            <Link className="btn" to={`/pay/${booking.id}`}>Complete payment</Link>
          )}
          <Link className="btn btn-ghost" to="/bookings">My bookings</Link>
        </div>
      </div>
    </section>
  )
}
