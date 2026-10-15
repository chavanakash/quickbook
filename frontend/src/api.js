// Thin wrapper around fetch: adds the JWT, parses errors into readable messages.
const TOKEN_KEY = 'qb_token'
const USER_KEY = 'qb_user'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function getUser() {
  const raw = localStorage.getItem(USER_KEY)
  return raw ? JSON.parse(raw) : null
}

export function saveSession({ access_token, user }) {
  localStorage.setItem(TOKEN_KEY, access_token)
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

export function errorMessage(data, fallback) {
  if (typeof data?.detail === 'string') return data.detail
  if (Array.isArray(data?.detail)) {
    return data.detail.map((e) => `${e.loc?.[e.loc.length - 1] ?? 'field'}: ${e.msg}`).join(', ')
  }
  return fallback
}

export async function api(path, { method = 'GET', body, raw = false } = {}) {
  const headers = {}
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  const res = await fetch(path, { method, headers, body: body !== undefined ? JSON.stringify(body) : undefined })

  if (res.status === 401 && token) {
    // Token expired: force a fresh sign-in.
    clearSession()
    window.location.assign('/signin')
    throw new Error('Session expired, please sign in again')
  }
  if (!res.ok) {
    const data = await res.json().catch(() => null)
    throw new Error(errorMessage(data, `Request failed (${res.status})`))
  }
  return raw ? res : res.json()
}

export async function downloadTicket(booking) {
  const res = await api(`/api/tickets/${booking.id}`, { raw: true })
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `ticket-${booking.pnr}.pdf`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
