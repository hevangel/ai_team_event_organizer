import type { AdminUserRow, AdminVotes, AppState } from './types'

export class ApiErr extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let message = `HTTP ${res.status}`
    try {
      const body = await res.json()
      message = body.error || message
    } catch {
      /* not JSON */
    }
    throw new ApiErr(res.status, message)
  }
  return res.json() as Promise<T>
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const api = {
  state: () => fetch('/api/state', { credentials: 'same-origin' }).then(handle<AppState>),
  login: (userid: string, displayName: string) =>
    fetch('/api/login', json('POST', { userid, display_name: displayName })).then(handle),
  logout: () => fetch('/api/logout', { method: 'POST' }).then(handle),
  saveVote: (body: { availability: { slot_id: number; level: string }[]; food_venue_ids: number[]; activity_venue_ids: number[] }) =>
    fetch('/api/vote', json('PUT', body)).then(handle<{ saved: boolean }>),
  suggestVenue: (body: Record<string, unknown>) =>
    fetch('/api/venues', json('POST', body)).then(handle<{ venue_id: number }>),

  adminUpdateSettings: (patch: Record<string, unknown>) =>
    fetch('/api/admin/settings', json('PUT', { patch })).then(handle),
  adminSetSlots: (slots: { date: string; start_time: string; end_time: string }[]) =>
    fetch('/api/admin/slots', json('PUT', { slots })).then(handle<{ slot_count: number }>),
  adminAddVenue: (fields: Record<string, unknown>) =>
    fetch('/api/admin/venues', json('POST', fields)).then(handle<{ venue_id: number }>),
  adminUpdateVenue: (id: number, fields: Record<string, unknown>) =>
    fetch(`/api/admin/venues/${id}`, json('PUT', fields)).then(handle),
  adminRemoveVenue: (id: number) =>
    fetch(`/api/admin/venues/${id}`, { method: 'DELETE' }).then(handle),
  adminVotes: () => fetch('/api/admin/votes', { credentials: 'same-origin' }).then(handle<AdminVotes>),
  adminUsers: () => fetch('/api/admin/users', { credentials: 'same-origin' }).then(handle<AdminUserRow[]>),
  adminSetAdmin: (targetUserId: string, isAdmin: boolean) =>
    fetch(`/api/admin/users/${encodeURIComponent(targetUserId)}/admin`, json('PUT', { is_admin: isAdmin })).then(
      handle<{ user_id: string; is_admin: boolean }>,
    ),
}
