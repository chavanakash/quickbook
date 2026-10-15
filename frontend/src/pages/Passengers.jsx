import { useEffect, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api.js'
import TripSummary from '../components/TripSummary.jsx'
import { formatPrice } from '../utils.js'

export default function Passengers() {
  const { scheduleId } = useParams()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const date = params.get('date')
  const count = Math.min(Math.max(Number(params.get('pax')) || 1, 1), 6)

  const [trip, setTrip] = useState(null)
  const [passengers, setPassengers] = useState(() => Array.from({ length: count }, () => ({ name: '', age: '' })))
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    api(`/api/inventory/schedules/${scheduleId}?date=${date}`).then(setTrip).catch((err) => setError(err.message))
  }, [scheduleId, date])

  function update(index, field, value) {
    setPassengers((list) => list.map((p, i) => (i === index ? { ...p, [field]: value } : p)))
  }

  async function submit(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const booking = await api('/api/bookings', {
        method: 'POST',
        body: {
          schedule_id: Number(scheduleId),
          travel_date: date,
          passengers: passengers.map((p) => ({ name: p.name.trim(), age: Number(p.age) })),
        },
      })
      navigate(`/pay/${booking.id}`)
    } catch (err) {
      setError(err.message)
      setLoading(false)
    }
  }

  if (!trip) return <section>{error ? <p className="error">{error}</p> : <p className="muted">Loading…</p>}</section>

  return (
    <section>
      <h1>Passenger details</h1>
      <div className="card"><TripSummary trip={trip} /></div>
      <form className="card" onSubmit={submit}>
        {passengers.map((p, i) => (
          <div key={i} className="passenger-row">
            <strong>Passenger {i + 1}</strong>
            <label>Full name<input required minLength={2} maxLength={80} value={p.name} onChange={(e) => update(i, 'name', e.target.value)} /></label>
            <label>Age<input type="number" required min={0} max={120} value={p.age} onChange={(e) => update(i, 'age', e.target.value)} /></label>
          </div>
        ))}
        <div className="total">
          <span>{count} × {formatPrice(trip.price)}</span>
          <strong>Total {formatPrice(trip.price * count)}</strong>
        </div>
        {error && <p className="error">{error}</p>}
        <button className="btn" disabled={loading}>{loading ? 'Reserving…' : 'Continue to payment'}</button>
      </form>
    </section>
  )
}
