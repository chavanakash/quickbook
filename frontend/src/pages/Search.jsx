import { useEffect, useState } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api.js'
import TripSummary from '../components/TripSummary.jsx'
import { formatPrice, todayISO } from '../utils.js'

export default function Search() {
  const { mode } = useParams()
  const navigate = useNavigate()
  const [cities, setCities] = useState([])
  const [form, setForm] = useState({ origin: '', destination: '', date: todayISO(), passengers: 1 })
  const [results, setResults] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (mode !== 'flight' && mode !== 'train') return
    setResults(null)
    api(`/api/inventory/locations?mode=${mode}`)
      .then((list) => {
        setCities(list)
        setForm((f) => ({ ...f, origin: list[0] ?? '', destination: list[1] ?? '' }))
      })
      .catch((err) => setError(err.message))
  }, [mode])

  if (mode !== 'flight' && mode !== 'train') return <Navigate to="/" replace />

  async function submit(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const params = new URLSearchParams({ mode, origin: form.origin, destination: form.destination, date: form.date })
      setResults(await api(`/api/inventory/search?${params}`))
    } catch (err) {
      setError(err.message)
      setResults(null)
    } finally {
      setLoading(false)
    }
  }

  function select(trip) {
    navigate(`/book/${trip.schedule_id}?date=${form.date}&pax=${form.passengers}`)
  }

  return (
    <section>
      <h1>Search {mode === 'flight' ? 'flights ✈️' : 'trains 🚆'}</h1>
      <form className="card search-form" onSubmit={submit}>
        <label>From
          <select value={form.origin} onChange={(e) => setForm({ ...form, origin: e.target.value })}>
            {cities.map((c) => <option key={c}>{c}</option>)}
          </select>
        </label>
        <label>To
          <select value={form.destination} onChange={(e) => setForm({ ...form, destination: e.target.value })}>
            {cities.map((c) => <option key={c}>{c}</option>)}
          </select>
        </label>
        <label>Date
          <input type="date" required min={todayISO()} value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
        </label>
        <label>Passengers
          <select value={form.passengers} onChange={(e) => setForm({ ...form, passengers: Number(e.target.value) })}>
            {[1, 2, 3, 4, 5, 6].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        <button className="btn" disabled={loading}>{loading ? 'Searching…' : 'Search'}</button>
      </form>

      {error && <p className="error">{error}</p>}

      {results && (
        <div className="results">
          {results.length === 0 && <p className="muted">No {mode}s found for this route.</p>}
          {results.map((trip) => (
            <div key={trip.schedule_id} className="card result">
              <TripSummary trip={trip} />
              <div className="result-action">
                <div className="price">{formatPrice(trip.price)}<span className="muted"> / person</span></div>
                <button className="btn" onClick={() => select(trip)}>Select</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
