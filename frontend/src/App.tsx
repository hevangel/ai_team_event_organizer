import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiErr } from './api'
import type { AppState, Level } from './types'
import AdminPanel from './components/AdminPanel'
import AvailabilityGrid from './components/AvailabilityGrid'
import Footer from './components/Footer'
import Login from './components/Login'
import ResultsPanel from './components/ResultsPanel'
import VenueSection from './components/VenueSection'
import { Toast } from './components/ui'

interface Draft {
  loadedFor: string
  availability: Record<number, Level>
  food: number[]
  activity: number[]
}

const POLL_MS = 5000

export default function App() {
  const [state, setState] = useState<AppState | null>(null)
  const [draft, setDraft] = useState<Draft | null>(null)
  const [adminOpen, setAdminOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [toast, setToast] = useState<string | null>(null)
  const toastTimer = useRef<number | undefined>(undefined)

  const showToast = useCallback((msg: string) => {
    setToast(msg)
    window.clearTimeout(toastTimer.current)
    toastTimer.current = window.setTimeout(() => setToast(null), 2600)
  }, [])

  const refresh = useCallback(async () => {
    try {
      setState(await api.state())
    } catch (e) {
      if (e instanceof ApiErr && e.status === 401) {
        setState((prev) => (prev ? { ...prev, authenticated: false, me: undefined } : prev))
      } else {
        showToast(e instanceof Error ? e.message : 'Cannot reach the server')
      }
    }
  }, [showToast])

  // Initial load + polling (skips while the tab is hidden).
  useEffect(() => {
    refresh()
    const id = window.setInterval(() => {
      if (!document.hidden) refresh()
    }, POLL_MS)
    return () => window.clearInterval(id)
  }, [refresh])

  // (Re)initialize the draft vote when the signed-in user changes. Polling
  // never clobbers an in-progress draft.
  const meId = state?.me?.user_id
  useEffect(() => {
    if (!state?.me) {
      setDraft(null)
      return
    }
    setDraft((prev) => {
      if (prev && prev.loadedFor === state.me!.user_id) return prev
      return {
        loadedFor: state.me!.user_id,
        availability: Object.fromEntries(
          Object.entries(state.my_availability || {}).map(([id, level]) => [Number(id), level as Level]),
        ),
        food: state.my_vote?.food_venue_ids || [],
        activity: state.my_vote?.activity_venue_ids || [],
      }
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meId])

  // An admin can delete slots or venues while a voter has an unsaved draft.
  // Polling picks the change up, so drop the options that no longer exist —
  // otherwise Save fails on an unknown id or submits a stale choice. Every
  // still-valid unsaved selection is preserved.
  const slotKey = state?.slots.map((s) => s.id).join(',') ?? ''
  const foodKey = state?.venues.filter((v) => v.type === 'food').map((v) => v.id).join(',') ?? ''
  const activityKey = state?.venues.filter((v) => v.type === 'activity').map((v) => v.id).join(',') ?? ''
  useEffect(() => {
    const ids = (key: string) => new Set(key ? key.split(',').map(Number) : [])
    const slots = ids(slotKey)
    const food = ids(foodKey)
    const activity = ids(activityKey)
    setDraft((d) => {
      if (!d) return d
      const availability = Object.fromEntries(
        Object.entries(d.availability).filter(([id]) => slots.has(Number(id))),
      ) as Record<number, Level>
      const nextFood = d.food.filter((id) => food.has(id))
      const nextActivity = d.activity.filter((id) => activity.has(id))
      const unchanged =
        Object.keys(availability).length === Object.keys(d.availability).length &&
        nextFood.length === d.food.length &&
        nextActivity.length === d.activity.length
      return unchanged ? d : { ...d, availability, food: nextFood, activity: nextActivity }
    })
  }, [slotKey, foodKey, activityKey])

  // First-run: admin signs into an unconfigured event -> admin view by default.
  useEffect(() => {
    if (state?.me?.is_admin && state.slots.length === 0 && state.venues.length === 0) {
      setAdminOpen(true)
    }
  }, [state?.me?.is_admin, state?.slots.length, state?.venues.length])

  if (!state) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-slate-400">Connecting…</div>
    )
  }

  if (!state.authenticated || !state.me) {
    return (
      <>
        <Login
          state={state}
          onLoggedIn={() => refresh()}
          onError={(e) => showToast(e instanceof Error ? e.message : 'Login failed')}
        />
        <Toast message={toast} />
      </>
    )
  }

  const me = state.me
  const readOnly = state.status.closed
  const headcountFull =
    !state.my_vote?.has_vote &&
    state.settings.headcount_limit != null &&
    (state.results?.headcount_taken ?? 0) >= state.settings.headcount_limit

  const sameSet = (a: number[], b: number[]) => JSON.stringify([...a].sort()) === JSON.stringify([...b].sort())
  const dirty =
    !!draft &&
    (JSON.stringify(Object.entries(draft.availability).map(([k, v]) => [Number(k), v]).sort()) !==
      JSON.stringify(
        Object.entries(state.my_availability || {}).map(([k, v]) => [Number(k), v as Level]).sort(),
      ) ||
      !sameSet(draft.food, state.my_vote?.food_venue_ids || []) ||
      !sameSet(draft.activity, state.my_vote?.activity_venue_ids || []))

  async function save() {
    if (!draft) return
    setSaving(true)
    try {
      await api.saveVote({
        availability: Object.entries(draft.availability).map(([slotId, level]) => ({
          slot_id: Number(slotId),
          level,
        })),
        food_venue_ids: draft.food,
        activity_venue_ids: draft.activity,
      })
      await refresh()
      showToast('Vote saved ✓')
    } catch (e) {
      showToast(e instanceof Error ? e.message : 'Save failed')
      if (e instanceof ApiErr && e.status === 403) refresh()
    } finally {
      setSaving(false)
    }
  }

  async function logout() {
    try {
      await api.logout()
    } catch {
      /* ignore */
    }
    setDraft(null)
    setAdminOpen(false)
    refresh()
  }

  return (
    <div className="min-h-full pb-28">
      <header className="sticky top-0 z-30 border-b border-slate-200/80 bg-white/85 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-3 sm:px-6">
          <span className="text-xl">🎉</span>
          <div className="min-w-0">
            <h1 className="truncate text-base font-bold text-slate-800">{state.settings.event_title}</h1>
            <p className="text-xs text-slate-400">
              {readOnly
                ? 'Voting is closed — results below'
                : `Hi ${me.display_name}, pick when you're free, then what to do`}
            </p>
          </div>
          <div className="ml-auto flex items-center gap-2">
            {me.is_admin && (
              <button className="btn-outline !px-3" title="Admin panel" onClick={() => setAdminOpen(true)}>
                ⚙️ <span className="hidden sm:inline">Admin</span>
              </button>
            )}
            <span className="chip bg-indigo-50 text-indigo-700">{me.display_name}</span>
            <button className="btn-ghost !px-2.5" title="Sign out" onClick={logout}>
              ⎋
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto grid max-w-7xl grid-cols-1 gap-6 px-4 py-6 sm:px-6 lg:grid-cols-[1fr_340px]">
        <div className="min-w-0 space-y-6">
          <section className="card">
            <h2 className="mb-1 text-lg font-bold text-slate-800">
              <span className="mr-2 text-indigo-500">1.</span>When are you free?
            </h2>
            <p className="mb-4 text-sm text-slate-400">
              Click the cells that work for you — not the ones that don't.
              {state.settings.preference_mode === 'strong_weak' &&
                ' Click again for a strong (★) or weak (~) preference.'}
              {' '}Or just tell your AI agent what to vote for.
            </p>
            <AvailabilityGrid
              slots={state.slots}
              draft={draft?.availability || {}}
              mode={state.settings.preference_mode}
              results={state.results}
              readOnly={readOnly || headcountFull}
              onChange={(slotId, level) =>
                setDraft((d) => {
                  if (!d) return d
                  const availability = { ...d.availability }
                  if (level === null) delete availability[slotId]
                  else availability[slotId] = level
                  return { ...d, availability }
                })
              }
            />
          </section>

          <section className="card">
            <h2 className="mb-1 text-lg font-bold text-slate-800">
              <span className="mr-2 text-indigo-500">2.</span>What should we do?
            </h2>
            <p className="mb-4 text-sm text-slate-400">
              Pick any food places and activities you're up for. It all updates live as the team votes.
            </p>
            <VenueSection
              state={state}
              draftFood={draft?.food || []}
              draftActivity={draft?.activity || []}
              readOnly={readOnly || headcountFull}
              onToggled={(food, activity) => setDraft((d) => (d ? { ...d, food, activity } : d))}
              onToast={showToast}
              onChanged={() => refresh()}
            />
          </section>
        </div>

        <aside className="lg:sticky lg:top-20 lg:self-start">
          <ResultsPanel state={state} draftDirty={dirty} />
        </aside>
      </main>

      {state.settings.show_footer_to_voters && (
        <div className="mx-auto max-w-7xl px-4 sm:px-6">
          <Footer footer={state.footer} />
        </div>
      )}

      <div className="fixed inset-x-0 bottom-0 z-30 border-t border-slate-200/70 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-3 sm:px-6">
          <span className={`text-sm ${dirty ? 'font-semibold text-amber-600' : 'text-slate-400'}`}>
            {readOnly
              ? 'Voting is closed — your saved vote and the results are shown above.'
              : headcountFull
                ? 'The event is full (headcount limit reached).'
                : dirty
                  ? 'You have unsaved changes.'
                  : state.my_vote?.has_vote
                    ? 'All saved — change anything and save again before voting closes.'
                    : 'Nothing saved yet.'}
          </span>
          <button
            className="btn-primary ml-auto !px-6 !py-2.5"
            disabled={saving || readOnly || headcountFull || !dirty}
            onClick={save}
          >
            {saving ? 'Saving…' : dirty ? '💾 Save my vote' : 'Saved ✓'}
          </button>
        </div>
      </div>

      {adminOpen && me.is_admin && (
        <AdminPanel state={state} onClose={() => setAdminOpen(false)} onToast={showToast} onChanged={() => refresh()} />
      )}

      <Toast message={toast} />
    </div>
  )
}
