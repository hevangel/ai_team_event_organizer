import { useState } from 'react'
import type { TimeSlot, Venue, VenueType } from '../types'
import { Modal } from './ui'
import { AddressSearch } from './AddressSearch'
import MapPanel from './MapPanel'

/**
 * Create/edit form for venues. Used by voters (live suggestions) and by the
 * admin (full venue management). Coordinates come from Places search or by
 * clicking the map; picking a place auto-fills the name and address.
 */
export default function VenueFormModal({
  title,
  submitLabel,
  initial,
  slots,
  mapsApiKey,
  office,
  showActive,
  busy,
  onSubmit,
  onClose,
}: {
  title: string
  submitLabel: string
  initial?: Venue | null
  slots: TimeSlot[]
  mapsApiKey: string
  office?: { lat: number; lng: number } | null
  showActive?: boolean
  busy?: boolean
  onSubmit: (fields: {
    name: string
    type: VenueType
    description: string
    estimated_cost: number | null
    address: string
    lat: number | null
    lng: number | null
    slot_ids: number[]
    active?: boolean
  }) => void
  onClose: () => void
}) {
  const [name, setName] = useState(initial?.name || '')
  const [type, setType] = useState<VenueType>(initial?.type || 'food')
  const [description, setDescription] = useState(initial?.description || '')
  const [cost, setCost] = useState(initial?.estimated_cost?.toString() ?? '')
  const [address, setAddress] = useState(initial?.address || '')
  const [coords, setCoords] = useState<{ lat: number | null; lng: number | null }>({
    lat: initial?.lat ?? null,
    lng: initial?.lng ?? null,
  })
  const [slotIds, setSlotIds] = useState<number[]>(initial?.slot_ids || [])
  const [active, setActive] = useState(initial?.active ?? true)

  const canSubmit = name.trim().length > 0

  function submit() {
    if (!canSubmit) return
    onSubmit({
      name: name.trim(),
      type,
      description: description.trim(),
      estimated_cost: cost === '' ? null : Number(cost),
      address,
      lat: coords.lat,
      lng: coords.lng,
      slot_ids: slotIds,
      ...(showActive ? { active } : {}),
    })
  }

  return (
    <Modal title={title} onClose={onClose} wide>
      <div className="space-y-4">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div className="sm:col-span-2">
            <label className="label">Venue name</label>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Sushi Zanmai" />
          </div>
          <div>
            <label className="label">Type</label>
            <div className="grid grid-cols-2 gap-1 rounded-xl bg-slate-100 p-1">
              {(['food', 'activity'] as VenueType[]).map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setType(t)}
                  className={`rounded-lg px-2 py-1.5 text-sm font-medium transition-colors ${
                    type === t ? (t === 'food' ? 'bg-orange-500 text-white' : 'bg-sky-500 text-white') : 'text-slate-500 hover:text-slate-700'
                  }`}
                >
                  {t === 'food' ? '🍽 Food' : '🎯 Activity'}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div>
          <label className="label">Description</label>
          <textarea
            className="input min-h-16"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What's good here? Why should the team pick it?"
          />
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label className="label">Estimated cost (per person, $)</label>
            <input className="input" type="number" min="0" step="0.01" value={cost} onChange={(e) => setCost(e.target.value)} placeholder="25" />
          </div>
          <div>
            <label className="label">Address</label>
            <AddressSearch
              apiKey={mapsApiKey}
              value={address}
              onChange={(v) => {
                setAddress(v.address)
                setCoords({ lat: v.lat, lng: v.lng })
                if (v.name) setName(v.name)
              }}
            />
          </div>
        </div>

        {mapsApiKey && (
          <div>
            <label className="label">Location</label>
            <MapPanel
              apiKey={mapsApiKey}
              center={office ?? null}
              fallbackCenter={office ?? null}
              venues={
                coords.lat != null && coords.lng != null
                  ? [{ id: -1, name: name || 'New venue', type, description: '', estimated_cost: null, address, lat: coords.lat, lng: coords.lng, suggested_by: null, suggester_name: null, slot_ids: [], active: true }]
                  : []
              }
              pickMode
              onPick={(p) => setCoords(p)}
              className="h-80"
            />
            <p className="mt-1 text-xs text-slate-400">
              {coords.lat != null && coords.lng != null
                ? `Pinned at ${coords.lat.toFixed(5)}, ${coords.lng.toFixed(5)} — search a place or click the map to move the pin.`
                : office
                  ? `Centered on the office — search a place or click the map to drop the pin.`
                  : 'No pin yet — search or click the map.'}
            </p>
          </div>
        )}

        {slots.length > 0 && (
          <div>
            <label className="label">Compatible date/time slots (empty = always)</label>
            <div className="flex flex-wrap gap-1.5">
              {slots.map((s) => {
                const on = slotIds.includes(s.id)
                return (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => setSlotIds(on ? slotIds.filter((i) => i !== s.id) : [...slotIds, s.id])}
                    className={`rounded-full border px-2.5 py-1 text-xs font-medium transition-colors ${
                      on ? 'border-indigo-500 bg-indigo-50 text-indigo-700' : 'border-slate-200 bg-white text-slate-500 hover:bg-slate-50'
                    }`}
                  >
                    {new Date(s.date + 'T12:00:00').toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })} {s.start_time}
                  </button>
                )
              })}
            </div>
          </div>
        )}

        {showActive && (
          <label className="flex items-center gap-2 text-sm text-slate-600">
            <input type="checkbox" className="h-4 w-4 rounded" checked={active} onChange={(e) => setActive(e.target.checked)} />
            Active (visible in the vote)
          </label>
        )}

        <div className="flex justify-end gap-2 pt-1">
          <button type="button" className="btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className="btn-primary" disabled={!canSubmit || busy} onClick={submit}>
            {submitLabel}
          </button>
        </div>
      </div>
    </Modal>
  )
}
