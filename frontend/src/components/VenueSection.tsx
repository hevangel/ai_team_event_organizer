import { useState } from 'react'
import { api } from '../api'
import type { AppState, TimeSlot, Venue, VenueType } from '../types'
import MapPanel from './MapPanel'
import VenueFormModal from './VenueFormModal'

function VenueCard({
  venue,
  selected,
  count,
  voters,
  compatible,
  disabled,
  onToggle,
  onHover,
}: {
  venue: Venue
  selected: boolean
  count?: number
  voters?: string[]
  compatible: 'ok' | 'mismatch' | 'unknown'
  disabled: boolean
  onToggle: () => void
  onHover?: (hovering: boolean) => void
}) {
  const accent = venue.type === 'food' ? 'orange' : 'sky'
  return (
    <button
      disabled={disabled}
      onClick={onToggle}
      onMouseEnter={() => onHover?.(true)}
      onMouseLeave={() => onHover?.(false)}
      onFocus={() => onHover?.(true)}
      onBlur={() => onHover?.(false)}
      className={`w-full rounded-xl border p-3 text-left transition-all ${
        selected
          ? accent === 'orange'
            ? 'border-orange-400 bg-orange-50/70 ring-2 ring-orange-300'
            : 'border-sky-400 bg-sky-50/70 ring-2 ring-sky-300'
          : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50'
      } ${disabled ? 'cursor-not-allowed opacity-70' : 'cursor-pointer'}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <span className="font-semibold text-slate-800">{venue.name}</span>
          {venue.estimated_cost != null && (
            <span className="ml-2 text-sm text-slate-500">~${venue.estimated_cost}</span>
          )}
        </div>
        <span
          className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[11px] font-bold ${
            selected ? (accent === 'orange' ? 'border-orange-500 bg-orange-500 text-white' : 'border-sky-500 bg-sky-500 text-white') : 'border-slate-300 text-transparent'
          }`}
        >
          ✓
        </span>
      </div>
      {venue.description && <p className="mt-1 line-clamp-2 text-xs text-slate-500">{venue.description}</p>}
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {venue.suggested_by && (
          <span className={`chip ${accent === 'orange' ? 'bg-orange-100 text-orange-700' : 'bg-sky-100 text-sky-700'}`}>
            ✍ {venue.suggester_name || venue.suggested_by}
          </span>
        )}
        {count != null && count > 0 && (
          <span className="chip bg-slate-100 text-slate-600" title={voters?.join(', ')}>
            {count} vote{count === 1 ? '' : 's'}
            {voters && voters.length > 0 && ` · ${voters.join(', ')}`}
          </span>
        )}
        {compatible === 'mismatch' && (
          <span className="chip bg-amber-100 text-amber-700" title="Doesn't overlap with your selected time slots">
            ⚠ time conflict
          </span>
        )}
      </div>
    </button>
  )
}

/** Food & activity venue voting with live results and map. */
export default function VenueSection({
  state,
  draftFood,
  draftActivity,
  readOnly,
  onToggled,
  onToast,
  onChanged,
}: {
  state: AppState
  draftFood: number[]
  draftActivity: number[]
  readOnly: boolean
  onToggled: (food: number[], activity: number[]) => void
  onToast: (msg: string) => void
  onChanged: () => void
}) {
  const [suggesting, setSuggesting] = useState<VenueType | null>(null)
  const [hoverId, setHoverId] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const { settings, venues, results, slots, config } = state

  const mapsKey = config.maps_api_key
  const mySlots = new Set(
    Object.entries(state.my_availability || {})
      .filter(([, level]) => level !== 'no')
      .map(([id]) => Number(id)),
  )

  function compatibility(v: Venue): 'ok' | 'mismatch' | 'unknown' {
    if (v.slot_ids.length === 0 || mySlots.size === 0) return 'unknown'
    return v.slot_ids.some((s) => mySlots.has(s)) ? 'ok' : 'mismatch'
  }

  async function submitSuggestion(fields: Record<string, unknown>) {
    setBusy(true)
    try {
      await api.suggestVenue(fields)
      setSuggesting(null)
      onChanged()
      onToast('Venue suggested — everyone can see it live ✓')
    } catch (e) {
      onToast(e instanceof Error ? e.message : 'Failed to suggest venue')
    } finally {
      setBusy(false)
    }
  }

  function column(vtype: VenueType) {
    const picks = vtype === 'food' ? draftFood : draftActivity
    const list = venues.filter((v) => v.type === vtype)
    const resultMap: Record<string, { count: number; voters?: string[] }> =
      vtype === 'food' ? (results?.food ?? {}) : (results?.activity ?? {})
    return (
      <div>
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-sm font-bold text-slate-700">
            {vtype === 'food' ? '🍽 Food' : '🎯 Activity'}
            <span className="ml-2 text-xs font-normal text-slate-400">
              {picks.length} selected
            </span>
          </h3>
        </div>
        <div className="space-y-2">
          {list.length === 0 && (
            <p className="rounded-xl bg-slate-50 px-3 py-4 text-center text-xs text-slate-400">
              No {vtype} venues yet.
            </p>
          )}
          {list.map((v) => (
            <VenueCard
              key={v.id}
              venue={v}
              selected={picks.includes(v.id)}
              count={results?.visible ? resultMap[String(v.id)]?.count : undefined}
              voters={results?.visible ? resultMap[String(v.id)]?.voters : undefined}
              compatible={compatibility(v)}
              disabled={readOnly}
              onHover={(hovering) => setHoverId(hovering ? v.id : null)}
              onToggle={() => {
                const next = picks.includes(v.id) ? picks.filter((i) => i !== v.id) : [...picks, v.id]
                onToggled(vtype === 'food' ? next : draftFood, vtype === 'food' ? draftActivity : next)
              }}
            />
          ))}
          {settings.allow_venue_suggestions && !readOnly && (
            <button
              className="btn-outline w-full border-dashed text-slate-500"
              onClick={() => setSuggesting(vtype)}
            >
              + Suggest a {vtype === 'food' ? 'food place' : 'activity'}
            </button>
          )}
        </div>
      </div>
    )
  }

  const withCoords = venues.filter((v) => v.lat != null && v.lng != null)
  const center =
    settings.office_lat != null && settings.office_lng != null
      ? { lat: settings.office_lat, lng: settings.office_lng }
      : null

  return (
    <div className="space-y-5">
      <div>
        <MapPanel
          apiKey={mapsKey}
          center={center}
          venues={withCoords}
          highlightId={hoverId}
          className="h-[420px]"
        />
        <p className="mt-2 text-xs text-slate-400">
          <span className="mr-4">🏢 office</span>
          <span className="mr-4 text-orange-500">🍽 food</span>
          <span className="text-sky-500">🎯 activity</span>
          <span className="ml-3 hidden text-slate-300 sm:inline">hover a choice to spot it on the map</span>
        </p>
      </div>
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
        {column('food')}
        {column('activity')}
      </div>

      {suggesting && (
        <VenueFormModal
          title={`Suggest a ${suggesting === 'food' ? 'food place' : 'activity'}`}
          submitLabel="Add to vote"
          slots={slots}
          mapsApiKey={mapsKey}
          office={center}
          initial={{ type: suggesting } as Venue}
          busy={busy}
          onSubmit={submitSuggestion}
          onClose={() => setSuggesting(null)}
        />
      )}
    </div>
  )
}

export type { TimeSlot }
