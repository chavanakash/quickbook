import { formatDate, formatDuration, formatTime } from '../utils.js'

export default function TripSummary({ trip }) {
  return (
    <div className="trip">
      <div>
        <div className="trip-operator">{trip.operator}</div>
        <div className="muted">{trip.code ?? trip.trip_code} · {formatDate(trip.departure_at)}</div>
      </div>
      <div className="trip-times">
        <div><strong>{formatTime(trip.departure_at)}</strong><div className="muted">{trip.origin}</div></div>
        <div className="muted trip-duration">
          {trip.duration_minutes ? formatDuration(trip.duration_minutes) : '→'}
        </div>
        <div><strong>{formatTime(trip.arrival_at)}</strong><div className="muted">{trip.destination}</div></div>
      </div>
    </div>
  )
}
