import { useEffect, useState } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api.js'
import TripSummary from '../components/TripSummary.jsx'
import { formatCardNumber, formatPrice, luhnValid } from '../utils.js'

export default function Payment() {
  const { bookingId } = useParams()
  const navigate = useNavigate()
  const [booking, setBooking] = useState(null)
  const [card, setCard] = useState({ card_holder: '', card_number: '', expiry: '', cvv: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    api(`/api/bookings/${bookingId}`).then(setBooking).catch((err) => setError(err.message))
  }, [bookingId])

  if (booking?.status === 'CONFIRMED') return <Navigate to={`/confirmation/${bookingId}`} replace />

  function formatExpiry(value) {
    const digits = value.replace(/\D/g, '').slice(0, 4)
    return digits.length > 2 ? `${digits.slice(0, 2)}/${digits.slice(2)}` : digits
  }

  async function submit(e) {
    e.preventDefault()
    setError('')
    if (!luhnValid(card.card_number)) {
      setError('Card number is not valid')
      return
    }
    setLoading(true)
    try {
      await api('/api/payments', {
        method: 'POST',
        body: { ...card, booking_id: Number(bookingId), card_number: card.card_number.replace(/\s/g, '') },
      })
      navigate(`/confirmation/${bookingId}`)
    } catch (err) {
      setError(err.message)
      setLoading(false)
    }
  }

  if (!booking) return <section>{error ? <p className="error">{error}</p> : <p className="muted">Loading…</p>}</section>

  return (
    <section>
      <h1>Payment</h1>
      <div className="card">
        <TripSummary trip={booking} />
        <div className="total">
          <span>PNR {booking.pnr} · {booking.passengers.length} passenger(s)</span>
          <strong>{formatPrice(booking.amount)}</strong>
        </div>
      </div>
      <form className="card" onSubmit={submit}>
        <p className="hint">
          Dummy gateway: use <code>4111 1111 1111 1111</code> (success) or <code>4000 0000 0000 0002</code> (declined),
          any future expiry and any 3-digit CVV.
        </p>
        <label>Name on card<input required minLength={2} value={card.card_holder} onChange={(e) => setCard({ ...card, card_holder: e.target.value })} /></label>
        <label>Card number<input required inputMode="numeric" placeholder="4111 1111 1111 1111" value={card.card_number} onChange={(e) => setCard({ ...card, card_number: formatCardNumber(e.target.value) })} /></label>
        <div className="row">
          <label>Expiry<input required placeholder="MM/YY" pattern="(0[1-9]|1[0-2])/\d{2}" value={card.expiry} onChange={(e) => setCard({ ...card, expiry: formatExpiry(e.target.value) })} /></label>
          <label>CVV<input required type="password" inputMode="numeric" pattern="\d{3,4}" maxLength={4} value={card.cvv} onChange={(e) => setCard({ ...card, cvv: e.target.value.replace(/\D/g, '') })} /></label>
        </div>
        {error && <p className="error">{error}</p>}
        <button className="btn" disabled={loading}>{loading ? 'Processing…' : `Pay ${formatPrice(booking.amount)}`}</button>
      </form>
    </section>
  )
}
