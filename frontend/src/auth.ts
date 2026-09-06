/**
 * Minimal client-side auth for SIH26127 demo purposes.
 * Uses sessionStorage — cleared when the tab closes.
 *
 * In production, replace with real JWT / OAuth.
 */

export const AUTH_KEY = 'ue_auth'

export interface AuthUser {
  name: string
  role: string
  loginTime: string
}

/** Hardcoded demo credentials — replace with real auth in production */
const DEMO_CREDENTIALS: Record<string, { password: string; name: string; role: string }> = {
  admin:     { password: 'admin123',    name: 'Admin Sharma',    role: 'System Administrator' },
  operator:  { password: 'operator123', name: 'Ops Controller',  role: 'Traffic Operator' },
  viewer:    { password: 'viewer123',   name: 'Guest Viewer',    role: 'Read-Only Access' },
}

export function login(username: string, password: string): AuthUser | null {
  if (typeof window === 'undefined') return null
  const cred = DEMO_CREDENTIALS[username.toLowerCase().trim()]
  if (!cred || cred.password !== password) return null
  const user: AuthUser = { name: cred.name, role: cred.role, loginTime: new Date().toISOString() }
  sessionStorage.setItem(AUTH_KEY, JSON.stringify(user))
  return user
}

export function getUser(): AuthUser | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = sessionStorage.getItem(AUTH_KEY)
    return raw ? (JSON.parse(raw) as AuthUser) : null
  } catch {
    return null
  }
}

export function logout(): void {
  if (typeof window === 'undefined') return
  sessionStorage.removeItem(AUTH_KEY)
}

export function isAuthenticated(): boolean {
  return getUser() !== null
}
