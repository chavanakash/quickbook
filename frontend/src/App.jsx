import { Navigate, Route, Routes } from 'react-router-dom'
import { getToken } from './api.js'
import NavBar from './components/NavBar.jsx'
import SignIn from './pages/SignIn.jsx'
import SignUp from './pages/SignUp.jsx'
import Home from './pages/Home.jsx'
import Search from './pages/Search.jsx'
import Passengers from './pages/Passengers.jsx'
import Payment from './pages/Payment.jsx'
import Confirmation from './pages/Confirmation.jsx'
import MyBookings from './pages/MyBookings.jsx'

function Protected({ children }) {
  return getToken() ? children : <Navigate to="/signin" replace />
}

export default function App() {
  return (
    <>
      <NavBar />
      <main className="container">
        <Routes>
          <Route path="/signin" element={<SignIn />} />
          <Route path="/signup" element={<SignUp />} />
          <Route path="/" element={<Protected><Home /></Protected>} />
          <Route path="/search/:mode" element={<Protected><Search /></Protected>} />
          <Route path="/book/:scheduleId" element={<Protected><Passengers /></Protected>} />
          <Route path="/pay/:bookingId" element={<Protected><Payment /></Protected>} />
          <Route path="/confirmation/:bookingId" element={<Protected><Confirmation /></Protected>} />
          <Route path="/bookings" element={<Protected><MyBookings /></Protected>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </>
  )
}
