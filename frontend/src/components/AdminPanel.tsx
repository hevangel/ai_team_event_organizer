import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import type { AdminUserRow, AdminVotes, AppState, Settings, TimeSlot, Venue } from '../types'
import { Modal, Toggle } from './ui'
import { AddressSearch } from './AddressSearch'
import MapPanel from './MapPanel'
import VenueFormModal from './VenueFormModal'
import Footer from './Footer'

type Tab = 'event' | 'schedule' | 'locations' | 'votes' | 'people'

const TABS: { id: Tab; label: string; icon: string }[] = [
  { id: 'event', label: 'Event', icon: '⚙️' },
  { id: 'schedule', label: 'Date & time', icon: '📅' },
  { id: 'locations', label: 'Locations', icon: '📍' },
  { id: 'votes', label: 'Votes', icon: '🗳️' },
  { id: 'people', label: 'People', icon: '👥' },
]

export default function AdminPanel({
  state,
  onClose,
  onToast,
  onChanged,
}: {
  state: AppState
  onClose: () => void
  onToast: (msg: string) => void
  onChanged: () => void
}) {
  const [tab, setTab] = useState<Tab>(state.slots.length === 0 ? 'schedule' : 'event')
  const mapsKey = state.config.maps_api_key

  return (
    <Modal title="Admin panel" onClose={onClose} wide tall>
      <div className="mb-4 flex gap-1 rounded-xl bg-slate-100 p-1">
        {TABS.map((t) => (
          <button
            key={t.id}
            className={`flex-1 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
              tab === t.id ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'
            }`}
            onClick={() => setTab(t.id)}
          >
            {t.icon} {t.label}
          </button>
        ))}
      </div>
      {tab === 'event' && <EventTab state={state} onToast={onToast} onChanged={onChanged} />}
      {tab === 'schedule' && <ScheduleTab state={state} onToast={onToast} onChanged={onChanged} />}
      {tab === 'locations' && <LocationsTab state={state} mapsKey={mapsKey} onToast={onToast} onChanged={onChanged} />}
      {tab === 'votes' && <VotesTab state={state} />}
      {tab === 'people' && <PeopleTab state={state} onToast={onToast} />}
      {/* The admin view always shows the AI-attribution footer. */}
      <Footer footer={state.footer} />
    </Modal>
  )
}

/* ------------------------------------------------------------------ Event */

function EventTab({
  state,
  onToast,
  onChanged,
}: {
  state: AppState
  onToast: (msg: string) => void
  onChanged: () => void
}) {
  const [form, setForm] = useState<Settings>({ ...state.settings })
  const [busy, setBusy] = useState(false)
  const set = (patch: Partial<Settings>) => setForm((f) => ({ ...f, ...patch }))

  async function save() {
    setBusy(true)
    try {
      await api.adminUpdateSettings({
        event_title: form.event_title,
        event_description: form.event_description,
        budget_amount: form.budget_amount,
        budget_type: form.budget_type,
        headcount_limit: form.headcount_limit,
        preference_mode: form.preference_mode,
        allow_venue_suggestions: form.allow_venue_suggestions,
        anonymous_voting: form.anonymous_voting,
        hide_live_counts: form.hide_live_counts,
        show_footer_to_voters: form.show_footer_to_voters,
        voting_closes_at: form.voting_closes_at,
        voting_closed: form.voting_closed,
      })
      onToast('Settings saved ✓')
      onChanged()
    } catch (e) {
      onToast(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <label className="label">Event title</label>
          <input className="input" value={form.event_title} onChange={(e) => set({ event_title: e.target.value })} />
        </div>
        <div className="sm:col-span-2">
          <label className="label">Description</label>
          <textarea className="input min-h-14" value={form.event_description} onChange={(e) => set({ event_description: e.target.value })} />
        </div>

        <div>
          <label className="label">Budget</label>
          <div className="flex gap-2">
            <input
              className="input"
              type="number"
              min="0"
              value={form.budget_amount ?? ''}
              placeholder="none"
              onChange={(e) => set({ budget_amount: e.target.value === '' ? null : Number(e.target.value) })}
            />
            <select
              className="input !w-36"
              value={form.budget_type}
              onChange={(e) => set({ budget_type: e.target.value as 'per_head' | 'total' })}
            >
              <option value="per_head">per head</option>
              <option value="total">total</option>
            </select>
          </div>
        </div>
        <div>
          <label className="label">Headcount limit</label>
          <input
            className="input"
            type="text"
            inputMode="numeric"
            placeholder="blank = no limit"
            value={form.headcount_limit ?? ''}
            onChange={(e) => {
              const digits = e.target.value.replace(/[^0-9]/g, '')
              set({ headcount_limit: digits === '' ? null : Math.max(1, Number(digits)) })
            }}
          />
          <p className="mt-1 text-xs text-slate-400">Leave blank for no limit — first come, first served.</p>
        </div>

        <div className="sm:col-span-2">
          <label className="label">Availability preference mode</label>
          <div className="grid grid-cols-2 gap-1 rounded-xl bg-slate-100 p-1">
            {(
              [
                ['simple', 'Simple — available yes/no'],
                ['strong_weak', 'Strong + weak preference'],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                onClick={() => set({ preference_mode: value })}
                className={`rounded-lg px-2 py-1.5 text-sm font-medium ${
                  form.preference_mode === value ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-500'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className="sm:col-span-2 divide-y divide-slate-100">
          <Toggle
            label="Allow live venue suggestions"
            hint="Voters can add new food/activity venues while voting."
            checked={form.allow_venue_suggestions}
            onChange={(v) => set({ allow_venue_suggestions: v })}
          />
          <Toggle
            label="Anonymous voting"
            hint="Nobody (not even the admin) can see who voted for what — counts only."
            checked={form.anonymous_voting}
            onChange={(v) => set({ anonymous_voting: v })}
          />
          <Toggle
            label="Hide live results"
            hint="Voters see no counts until voting closes."
            checked={form.hide_live_counts}
            onChange={(v) => set({ hide_live_counts: v })}
          />
          <Toggle
            label="Show AI footer to voters"
            hint="Repo link + which AI agent built this, with tokens/cost so far. The admin view always shows it."
            checked={form.show_footer_to_voters}
            onChange={(v) => set({ show_footer_to_voters: v })}
          />
        </div>

        <div>
          <label className="label">Voting closes at</label>
          <input
            className="input"
            type="datetime-local"
            value={form.voting_closes_at ?? ''}
            onChange={(e) => set({ voting_closes_at: e.target.value || null })}
          />
        </div>
        <div className="flex items-end">
          <div className="w-full rounded-xl border border-rose-100 bg-rose-50/60 px-3 py-2">
            <Toggle
              label="Close voting now"
              hint="Manual switch; re-open anytime."
              checked={form.voting_closed}
              onChange={(v) => set({ voting_closed: v })}
            />
          </div>
        </div>
      </div>

      <div className="flex justify-end">
        <button className="btn-primary" disabled={busy} onClick={save}>
          {busy ? 'Saving…' : 'Save settings'}
        </button>
      </div>
    </div>
  )
}

/* --------------------------------------------------------------- Schedule */

const RANGE_PRESETS = [
  { label: 'Lunch 11:00–14:00', start: '11:00', end: '14:00' },
  { label: 'Afternoon 14:00–17:00', start: '14:00', end: '17:00' },
  { label: 'Dinner 17:00–21:00', start: '17:00', end: '21:00' },
  { label: 'Workday 09:00–17:00', start: '09:00', end: '17:00' },
]

function* monthDates(year: number, month: number): Generator<Date | null> {
  const first = new Date(year, month, 1)
  const startOffset = (first.getDay() + 6) % 7 // Monday-first
  for (let i = 0; i < startOffset; i++) yield null
  const days = new Date(year, month + 1, 0).getDate()
  for (let d = 1; d <= days; d++) yield new Date(year, month, d)
}

function ScheduleTab({
  state,
  onToast,
  onChanged,
}: {
  state: AppState
  onToast: (msg: string) => void
  onChanged: () => void
}) {
  const [slots, setSlots] = useState<TimeSlot[]>(state.slots)
  const [month, setMonth] = useState(() => new Date())
  const [selectedDates, setSelectedDates] = useState<Set<string>>(new Set())
  const [ranges, setRanges] = useState([{ start: '11:00', end: '14:00' }])
  const [busy, setBusy] = useState(false)

  const cells = useMemo(() => Array.from(monthDates(month.getFullYear(), month.getMonth())), [month])
  const yearMonthLabel = month.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })

  function toggleDate(iso: string) {
    setSelectedDates((prev) => {
      const next = new Set(prev)
      if (next.has(iso)) next.delete(iso)
      else next.add(iso)
      return next
    })
  }

  function toggleWeek(rowDates: (Date | null)[]) {
    const isos = rowDates.filter(Boolean).map((d) => (d as Date).toISOString().slice(0, 10))
    const allSelected = isos.every((i) => selectedDates.has(i))
    setSelectedDates((prev) => {
      const next = new Set(prev)
      isos.forEach((i) => (allSelected ? next.delete(i) : next.add(i)))
      return next
    })
  }

  function applyRanges() {
    const next = [...slots]
    // Unsaved rows need their own ids: a shared -1 makes React reuse the wrong
    // row identity and the per-slot remove button delete the wrong chip.
    let tempId = Math.min(0, ...next.map((s) => s.id)) - 1
    for (const iso of selectedDates) {
      for (const r of ranges) {
        const dup = next.some((s) => s.date === iso && s.start_time === r.start && s.end_time === r.end)
        if (!dup && r.start < r.end) {
          next.push({ id: tempId, date: iso, start_time: r.start, end_time: r.end })
          tempId -= 1
        }
      }
    }
    next.sort((a, b) => (a.date + a.start_time).localeCompare(b.date + b.start_time))
    setSlots(next)
    setSelectedDates(new Set())
  }

  // Compare contents, not just the count: editing a slot's date or time keeps
  // the count identical, and a count-only check left Save disabled.
  const pending = normalizeSlots(slots) !== normalizeSlots(state.slots)

  async function save() {
    setBusy(true)
    try {
      const res = await api.adminSetSlots(
        slots.map(({ date, start_time, end_time }) => ({ date, start_time, end_time })),
      )
      onToast(`Schedule saved — ${res.slot_count} slots ✓`)
      onChanged()
    } catch (e) {
      onToast(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  const byDate = slots.reduce<Record<string, TimeSlot[]>>((acc, s) => {
    ;(acc[s.date] ||= []).push(s)
    return acc
  }, {})

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <div>
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-sm font-bold text-slate-700">1. Pick dates (click, or whole weeks)</h3>
          <div className="flex items-center gap-1">
            <button className="btn-ghost !px-2 !py-1" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1))}>
              ‹
            </button>
            <span className="w-32 text-center text-sm font-semibold">{yearMonthLabel}</span>
            <button className="btn-ghost !px-2 !py-1" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1))}>
              ›
            </button>
          </div>
        </div>
        <div className="rounded-xl border border-slate-200 p-2">
          <div className="grid grid-cols-[24px_repeat(7,1fr)] gap-1 text-center">
            <span />
            {['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'].map((d) => (
              <span key={d} className="text-[10px] font-semibold text-slate-400">
                {d}
              </span>
            ))}
            {chunkWeeks(cells).map((week, wi) => (
              <WeekRow key={wi} week={week} selectedDates={selectedDates} month={month} onToggleDate={toggleDate} onToggleWeek={() => toggleWeek(week)} />
            ))}
          </div>
        </div>

        <h3 className="mt-4 mb-2 text-sm font-bold text-slate-700">2. Time slots</h3>
        <div className="space-y-2">
          {ranges.map((r, i) => (
            <div key={i} className="flex items-center gap-2">
              <input
                type="time"
                className="input !w-28"
                value={r.start}
                onChange={(e) => setRanges(ranges.map((x, j) => (j === i ? { ...x, start: e.target.value } : x)))}
              />
              <span className="text-slate-400">–</span>
              <input
                type="time"
                className="input !w-28"
                value={r.end}
                onChange={(e) => setRanges(ranges.map((x, j) => (j === i ? { ...x, end: e.target.value } : x)))}
              />
              <button className="btn-ghost !px-2 text-rose-500" onClick={() => setRanges(ranges.filter((_, j) => j !== i))}>
                ×
              </button>
            </div>
          ))}
        </div>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {RANGE_PRESETS.map((p) => (
            <button key={p.label} className="chip border border-slate-200 bg-white text-slate-500 hover:bg-slate-50" onClick={() => setRanges([...ranges, { start: p.start, end: p.end }])}>
              + {p.label}
            </button>
          ))}
          <button className="chip bg-indigo-50 text-indigo-600 hover:bg-indigo-100" onClick={() => setRanges([...ranges, { start: '09:00', end: '10:00' }])}>
            + custom
          </button>
        </div>

        <button className="btn-primary mt-4 w-full" disabled={selectedDates.size === 0} onClick={applyRanges}>
          Apply {ranges.length} slot{ranges.length === 1 ? '' : 's'} to {selectedDates.size} date{selectedDates.size === 1 ? '' : 's'}
        </button>
      </div>

      <div className="flex flex-col">
        <h3 className="mb-2 text-sm font-bold text-slate-700">
          Schedule ({slots.length} slots)
          {pending && <span className="ml-2 chip bg-amber-100 text-amber-700">unsaved</span>}
        </h3>
        <div className="min-h-40 flex-1 space-y-3 overflow-y-auto rounded-xl bg-slate-50 p-3">
          {slots.length === 0 && <p className="py-6 text-center text-xs text-slate-400">No slots yet — pick dates on the left.</p>}
          {Object.entries(byDate).map(([date, daySlots]) => (
            <div key={date}>
              <div className="mb-1 flex items-center justify-between text-xs font-semibold text-slate-600">
                {new Date(date + 'T12:00:00').toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' })}
                <button
                  className="text-slate-400 hover:text-rose-500"
                  onClick={() => setSlots(slots.filter((s) => s.date !== date))}
                >
                  remove date
                </button>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {daySlots.map((s) => (
                  <span key={s.id} className="chip border border-slate-200 bg-white text-slate-600">
                    {s.start_time}–{s.end_time}
                    <button className="ml-0.5 text-slate-300 hover:text-rose-500" onClick={() => setSlots(slots.filter((x) => x.id !== s.id))}>
                      ×
                    </button>
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
        <button className="btn-primary mt-3" disabled={busy || !pending} onClick={save}>
          {busy ? 'Saving…' : 'Save schedule'}
        </button>
        <p className="mt-2 text-xs text-slate-400">
          Slots you keep are left untouched, so voters keep their availability for them. Only
          removed slots lose their availability; venue votes are unaffected.
        </p>
      </div>
    </div>
  )
}

/** Order-independent, id-independent fingerprint of a schedule. */
function normalizeSlots(slots: TimeSlot[]): string {
  return slots
    .map((s) => `${s.date}T${s.start_time}-${s.end_time}`)
    .sort()
    .join('|')
}

function chunkWeeks(cells: (Date | null)[]): (Date | null)[][] {
  const weeks: (Date | null)[][] = []
  for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7))
  return weeks
}

function WeekRow({
  week,
  selectedDates,
  month,
  onToggleDate,
  onToggleWeek,
}: {
  week: (Date | null)[]
  selectedDates: Set<string>
  month: Date
  onToggleDate: (iso: string) => void
  onToggleWeek: () => void
}) {
  const isos = week.filter(Boolean).map((d) => (d as Date).toISOString().slice(0, 10))
  const allSelected = isos.length > 0 && isos.every((i) => selectedDates.has(i))
  return (
    <>
      <button
        className={`text-[10px] ${allSelected ? 'text-indigo-600' : 'text-slate-300 hover:text-indigo-400'}`}
        title="Toggle whole week"
        onClick={onToggleWeek}
      >
        ▸
      </button>
      {week.map((d, di) => {
        if (!d) return <span key={di} />
        const iso = d.toISOString().slice(0, 10)
        const inMonth = d.getMonth() === month.getMonth()
        const selected = selectedDates.has(iso)
        const isToday = new Date().toDateString() === d.toDateString()
        return (
          <button
            key={iso}
            onClick={() => onToggleDate(iso)}
            className={`mx-auto flex h-7 w-7 items-center justify-center rounded-full text-xs font-medium transition-colors ${
              selected
                ? 'bg-indigo-600 text-white'
                : inMonth
                  ? 'text-slate-700 hover:bg-indigo-100'
                  : 'text-slate-300 hover:bg-slate-100'
            } ${isToday && !selected ? 'ring-1 ring-indigo-400' : ''}`}
          >
            {d.getDate()}
          </button>
        )
      })}
    </>
  )
}

/* -------------------------------------------------------------- Locations */

function LocationsTab({
  state,
  mapsKey,
  onToast,
  onChanged,
}: {
  state: AppState
  mapsKey: string
  onToast: (msg: string) => void
  onChanged: () => void
}) {
  const [address, setAddress] = useState(state.settings.office_address)
  const [coords, setCoords] = useState<{ lat: number | null; lng: number | null }>({
    lat: state.settings.office_lat,
    lng: state.settings.office_lng,
  })
  const [editing, setEditing] = useState<Venue | 'new' | null>(null)
  const [busy, setBusy] = useState(false)
  const office = coords.lat != null && coords.lng != null ? { lat: coords.lat, lng: coords.lng } : null
  const withCoords = state.venues.filter((v) => v.lat != null && v.lng != null)

  async function saveOffice() {
    setBusy(true)
    try {
      await api.adminUpdateSettings({ office_address: address, office_lat: coords.lat, office_lng: coords.lng })
      onToast('Office location saved ✓')
      onChanged()
    } catch (e) {
      onToast(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  async function submitVenue(fields: Record<string, unknown>) {
    try {
      if (editing === 'new') await api.adminAddVenue(fields)
      else if (editing) await api.adminUpdateVenue(editing.id, fields)
      setEditing(null)
      onToast('Venue saved ✓')
      onChanged()
    } catch (e) {
      onToast(e instanceof Error ? e.message : 'Save failed')
    }
  }

  async function removeVenue(v: Venue) {
    try {
      await api.adminRemoveVenue(v.id)
      onToast(`Removed ${v.name}`)
      onChanged()
    } catch (e) {
      onToast(e instanceof Error ? e.message : 'Remove failed')
    }
  }

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <div>
        <h3 className="mb-2 text-sm font-bold text-slate-700">Office location</h3>
        <p className="mb-2 text-xs text-slate-400">Centers the voters' map. Search by name or address, or click the map.</p>
        <AddressSearch
          apiKey={mapsKey}
          value={address}
          placeholder="Search the office address…"
          onChange={(v) => {
            setAddress(v.address)
            if (v.lat != null && v.lng != null) setCoords({ lat: v.lat, lng: v.lng })
          }}
        />
        {!mapsKey && <p className="mt-1 text-xs text-slate-400">Add a Google Maps API key below to enable search.</p>}
        <MapPanel
          apiKey={mapsKey}
          center={office}
          venues={withCoords}
          pickMode
          onPick={(p) => setCoords(p)}
          className="mt-2 h-80"
        />
        <div className="mt-2 flex items-center justify-between">
          <span className="text-xs text-slate-400">
            {coords.lat != null && coords.lng != null
              ? `${coords.lat.toFixed(5)}, ${coords.lng.toFixed(5)}`
              : 'no pin set'}
          </span>
          <button className="btn-primary" disabled={busy} onClick={saveOffice}>
            Save office
          </button>
        </div>
        <div className="mt-4 rounded-xl bg-slate-50 p-3">
          <label className="label">Google Maps API key (optional)</label>
          <input
            className="input"
            placeholder="AIza… (leave empty to use server env var)"
            defaultValue={state.settings.google_maps_api_key}
            onBlur={async (e) => {
              if (e.target.value !== state.settings.google_maps_api_key) {
                await api.adminUpdateSettings({ google_maps_api_key: e.target.value })
                onToast('Maps key saved — reload to apply')
                onChanged()
              }
            }}
          />
          <p className="mt-1 text-xs text-slate-400">Needs “Maps JavaScript API” + “Places API” enabled.</p>
        </div>
      </div>

      <div>
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-sm font-bold text-slate-700">Event venues ({state.venues.length})</h3>
          <button className="btn-primary !py-1.5" onClick={() => setEditing('new')}>
            + Add venue
          </button>
        </div>
        <div className="max-h-[28rem] space-y-2 overflow-y-auto pr-1">
          {state.venues.map((v) => (
            <div key={v.id} className="flex items-start justify-between gap-2 rounded-xl border border-slate-200 p-3">
              <div>
                <span className="mr-2 chip bg-slate-100">{v.type === 'food' ? '🍽' : '🎯'}</span>
                <span className="font-semibold text-slate-800">{v.name}</span>
                {v.estimated_cost != null && <span className="ml-1.5 text-sm text-slate-500">~${v.estimated_cost}</span>}
                <p className="mt-0.5 text-xs text-slate-400">
                  {v.address || 'no address'}
                  {v.suggested_by && ` · suggested by ${v.suggester_name || v.suggested_by}`}
                  {v.slot_ids.length > 0 && ` · ${v.slot_ids.length} slot${v.slot_ids.length === 1 ? '' : 's'}`}
                </p>
              </div>
              <div className="flex shrink-0 gap-1">
                <button className="btn-ghost !px-2 !py-1 text-xs" onClick={() => setEditing(v)}>
                  Edit
                </button>
                <button className="btn-danger !px-2 !py-1 text-xs" onClick={() => removeVenue(v)}>
                  Remove
                </button>
              </div>
            </div>
          ))}
          {state.venues.length === 0 && (
            <p className="rounded-xl bg-slate-50 px-4 py-8 text-center text-xs text-slate-400">
              No venues yet — add food and activity options for the team to vote on.
            </p>
          )}
        </div>
      </div>

      {editing && (
        <VenueFormModal
          title={editing === 'new' ? 'Add venue' : `Edit ${editing.name}`}
          submitLabel="Save venue"
          initial={editing === 'new' ? null : editing}
          slots={state.slots}
          mapsApiKey={mapsKey}
          office={office}
          showActive
          onSubmit={submitVenue}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ Votes */

function VotesTab({ state }: { state: AppState }) {
  const [votes, setVotes] = useState<AdminVotes | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .adminVotes()
      .then(setVotes)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'))
  }, [])

  if (error) return <p className="rounded-xl bg-rose-50 px-4 py-6 text-center text-sm text-rose-600">{error}</p>
  if (!votes) return <p className="py-10 text-center text-sm text-slate-400">Loading votes…</p>

  const venueName = (id: number) => state.venues.find((v) => v.id === id)?.name ?? `#${id}`

  if (votes.anonymous) {
    return (
      <div>
        <p className="mb-3 rounded-xl bg-slate-50 px-4 py-3 text-xs text-slate-500">
          🔒 Voting is anonymous — per-person detail is hidden from everyone, including admins.
        </p>
        <AggregateResults votes={votes} venueName={venueName} />
      </div>
    )
  }

  const slots = votes.slots
  const people = votes.people.filter((p) => p.has_vote)

  return (
    <div className="space-y-4">
      <p className="text-xs text-slate-400">
        {people.length} vote{people.length === 1 ? '' : 's'} saved{votes.closed ? ' · voting closed' : ' · live'}
      </p>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-xs">
          <thead>
            <tr className="border-b border-slate-200 text-left text-slate-400">
              <th className="py-2 pr-3 font-semibold">Person</th>
              {slots.map((s) => (
                <th key={s.id} className="px-2 py-2 text-center font-semibold">
                  {new Date(s.date + 'T12:00:00').toLocaleDateString(undefined, { weekday: 'short', day: 'numeric' })}
                  <br />
                  {s.start_time}
                </th>
              ))}
              <th className="px-2 py-2 font-semibold">Food</th>
              <th className="px-2 py-2 font-semibold">Activity</th>
            </tr>
          </thead>
          <tbody>
            {people.map((p, i) => (
              <tr key={p.user_id ?? i} className="border-b border-slate-100">
                <td className="py-2 pr-3 font-medium whitespace-nowrap text-slate-700">{p.display_name}</td>
                {slots.map((s) => {
                  const level = p.availability[String(s.id)]
                  return (
                    <td key={s.id} className="px-2 py-2 text-center">
                      <span
                        className={`inline-block h-5 w-8 rounded ${
                          level === 'strong'
                            ? 'bg-violet-300'
                            : level === 'weak'
                              ? 'bg-amber-200'
                              : level === 'yes'
                                ? 'bg-emerald-200'
                                : 'bg-slate-100'
                        }`}
                        title={level || 'not available'}
                      />
                    </td>
                  )
                })}
                <td className="px-2 py-2 text-slate-600">{p.food_venue_ids.map(venueName).join(', ')}</td>
                <td className="px-2 py-2 text-slate-600">{p.activity_venue_ids.map(venueName).join(', ')}</td>
              </tr>
            ))}
            {people.length === 0 && (
              <tr>
                <td colSpan={slots.length + 3} className="py-8 text-center text-slate-400">
                  No votes yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <AggregateResults votes={votes} venueName={venueName} />
    </div>
  )
}

/* ------------------------------------------------------------------ People */

function PeopleTab({ state, onToast }: { state: AppState; onToast: (msg: string) => void }) {
  const [users, setUsers] = useState<AdminUserRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [newId, setNewId] = useState('')
  const [busy, setBusy] = useState(false)
  const meId = state.me?.user_id

  function load() {
    api
      .adminUsers()
      .then(setUsers)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'))
  }
  useEffect(() => {
    load()
  }, [])

  async function setAdmin(target: string, isAdmin: boolean) {
    setBusy(true)
    try {
      await api.adminSetAdmin(target, isAdmin)
      onToast(isAdmin ? `${target} is now an admin ✓` : `Admin access revoked for ${target}`)
      load()
    } catch (e) {
      onToast(e instanceof Error ? e.message : 'Change failed')
    } finally {
      setBusy(false)
    }
  }

  if (error) return <p className="rounded-xl bg-rose-50 px-4 py-6 text-center text-sm text-rose-600">{error}</p>
  if (!users) return <p className="py-10 text-center text-sm text-slate-400">Loading users…</p>
  const adminCount = users.filter((u) => u.is_admin).length

  return (
    <div className="space-y-4">
      <p className="text-xs text-slate-400">
        Admins can configure the event and see the Votes tab. An admin cannot revoke their own
        access, and the last admin cannot be demoted.
      </p>

      <div className="max-h-80 space-y-2 overflow-y-auto pr-1">
        {users.map((u) => (
          <div key={u.user_id} className="flex items-center justify-between gap-3 rounded-xl border border-slate-200 p-3">
            <div className="min-w-0">
              <span className="font-semibold text-slate-800">{u.display_name}</span>
              <span className="ml-2 text-xs text-slate-400">{u.user_id}</span>
              <div className="mt-0.5 flex flex-wrap gap-1.5">
                {u.is_admin && <span className="chip bg-indigo-100 text-indigo-700">admin</span>}
                {u.has_vote && <span className="chip bg-emerald-100 text-emerald-700">voted</span>}
                {u.user_id === meId && <span className="chip bg-slate-100 text-slate-500">you</span>}
              </div>
            </div>
            {u.is_admin ? (
              <button
                className="btn-danger shrink-0 !py-1.5 text-xs"
                disabled={busy || u.user_id === meId || adminCount <= 1}
                title={
                  u.user_id === meId
                    ? 'Ask another admin to revoke your access'
                    : adminCount <= 1
                      ? 'Cannot revoke the last admin'
                      : 'Revoke admin access'
                }
                onClick={() => setAdmin(u.user_id, false)}
              >
                Revoke admin
              </button>
            ) : (
              <button className="btn-outline shrink-0 !py-1.5 text-xs" disabled={busy} onClick={() => setAdmin(u.user_id, true)}>
                Make admin
              </button>
            )}
          </div>
        ))}
        {users.length === 0 && (
          <p className="rounded-xl bg-slate-50 px-4 py-8 text-center text-xs text-slate-400">No users have signed in yet.</p>
        )}
      </div>

      <div className="rounded-xl bg-slate-50 p-3">
        <label className="label">Grant admin to someone who hasn't signed in yet</label>
        <div className="flex gap-2">
          <input
            className="input"
            placeholder="their userid, e.g. carol"
            value={newId}
            onChange={(e) => setNewId(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && newId.trim()) setAdmin(newId.trim(), true)
            }}
          />
          <button className="btn-primary shrink-0" disabled={busy || !newId.trim()} onClick={() => setAdmin(newId.trim(), true)}>
            Grant admin
          </button>
        </div>
        <p className="mt-1 text-xs text-slate-400">Creates the user if needed; the flag waits for them at first login.</p>
      </div>
    </div>
  )
}

function AggregateResults({ votes, venueName }: { votes: AdminVotes; venueName: (id: number) => string }) {  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      <div className="rounded-xl bg-slate-50 p-3">
        <h4 className="mb-1.5 text-xs font-semibold text-slate-400 uppercase">Availability totals</h4>
        {votes.slots.map((s) => {
          const c = votes.results.availability[String(s.id)]
          return (
            <div key={s.id} className="flex justify-between py-0.5 text-xs">
              <span className="text-slate-500">
                {new Date(s.date + 'T12:00:00').toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })} {s.start_time}
              </span>
              <span className="font-semibold text-slate-700">{c?.total ?? 0}</span>
            </div>
          )
        })}
      </div>
      <div className="rounded-xl bg-slate-50 p-3">
        <h4 className="mb-1.5 text-xs font-semibold text-slate-400 uppercase">Venue votes</h4>
        {(['food', 'activity'] as const).map((kind) =>
          Object.entries(votes.results[kind]).map(([id, r]) => (
            <div key={kind + id} className="flex justify-between py-0.5 text-xs">
              <span className="text-slate-500">
                {kind === 'food' ? '🍽' : '🎯'} {venueName(Number(id))}
              </span>
              <span className="font-semibold text-slate-700">{r.count}</span>
            </div>
          )),
        )}
      </div>
    </div>
  )
}
