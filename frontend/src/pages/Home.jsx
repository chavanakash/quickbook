import { Link } from 'react-router-dom'

export default function Home() {
  return (
    <section>
      <h1>Where are you going?</h1>
      <p className="muted">Choose how you want to travel.</p>
      <div className="mode-grid">
        <Link to="/search/flight" className="card mode-card">
          <span className="mode-icon">✈️</span>
          <h2>Flights</h2>
          <p className="muted">Fastest way between cities</p>
        </Link>
        <Link to="/search/train" className="card mode-card">
          <span className="mode-icon">🚆</span>
          <h2>Trains</h2>
          <p className="muted">Comfortable and affordable</p>
        </Link>
      </div>
    </section>
  )
}
