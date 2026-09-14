import { useState } from 'react'
import { api } from '../api'
import type { AppState } from '../types'
import McpSetup from './McpSetup'

export default function Login({
  state,
  onLoggedIn,
  onError,
}: {
  state: AppState
  onLoggedIn: () => void
  onError: (e: unknown) => void
}) {
  const [userid, setUserid] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [busy, setBusy] = useState(false)
  const { settings, config } = state

  async function signIn() {
    if (!userid.trim()) return
    setBusy(true)
    try {
      await api.login(userid.trim(), displayName.trim())
      onLoggedIn()
    } catch (e) {
      onError(e)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center bg-gradient-to-br from-indigo-50 via-slate-100 to-violet-50 p-4">
      <div className="w-full max-w-md">
        <div className="card !p-8 text-center shadow-xl">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-500 text-3xl shadow-lg">
            🎉
          </div>
          <h1 className="text-2xl font-bold text-slate-800">{settings.event_title}</h1>
          {settings.event_description && (
            <p className="mt-2 text-sm text-slate-500">{settings.event_description}</p>
          )}

          <div className="mt-8 space-y-3 text-left">
            {config.testing_mode ? (
              <>
                <div>
                  <label className="label" htmlFor="userid">
                    Sign in with your userid
                  </label>
                  <input
                    id="userid"
                    className="input"
                    placeholder="e.g. alice"
                    autoFocus
                    value={userid}
                    onChange={(e) => setUserid(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && signIn()}
                  />
                </div>
                <div>
                  <label className="label" htmlFor="dn">
                    Display name <span className="font-normal normal-case">(optional)</span>
                  </label>
                  <input
                    id="dn"
                    className="input"
                    placeholder="e.g. Alice Chen"
                    value={displayName}
                    onChange={(e) => setDisplayName(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && signIn()}
                  />
                </div>
                <button className="btn-primary w-full !py-2.5" disabled={busy || !userid.trim()} onClick={signIn}>
                  {busy ? 'Signing in…' : 'Sign in'}
                </button>
              </>
            ) : (
              <p className="rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-700">
                Testing-mode login is disabled on this server.
              </p>
            )}

            {config.okta_enabled && (
              <>
                <div className="flex items-center gap-3 py-1 text-xs text-slate-400">
                  <span className="h-px flex-1 bg-slate-200" />
                  or
                  <span className="h-px flex-1 bg-slate-200" />
                </div>
                <a
                  href="/api/auth/okta/login"
                  className="btn-outline w-full !py-2.5 font-semibold text-indigo-700"
                >
                  Sign in with Okta SSO
                </a>
              </>
            )}
          </div>
        </div>

        <McpSetup config={config} />
      </div>
    </div>
  )
}
