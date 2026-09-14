import { useCallback, useEffect, useRef, useState } from 'react'
import { loadGoogleMaps } from './ui'

export interface PlaceSelection {
  address: string
  name: string
  lat: number | null
  lng: number | null
}

interface Prediction {
  placeId: string
  main: string
  secondary: string
  desc: string
}

/** Google Places JS API — which details to fetch for the picked place. */
const PLACE_DETAIL_FIELDS = ['name', 'formatted_address', 'geometry']

/**
 * Address input backed by Google Places predictions when a Maps key is
 * available; otherwise a plain text input. Reports the formatted address,
 * coordinates and the place name (for auto-filling a venue name).
 *
 * Built on AutocompleteService with a small dropdown of our own instead of
 * the Autocomplete widget, so the input node is stable across successive
 * searches and the dropdown styling matches the app.
 */
export function AddressSearch({
  apiKey,
  value,
  onChange,
  placeholder,
}: {
  apiKey: string
  value: string
  onChange: (v: PlaceSelection) => void
  placeholder?: string
}) {
  const inputRef = useRef<HTMLInputElement | null>(null)
  const [mapsReady, setMapsReady] = useState(() => !!window.google?.maps?.places)
  const [items, setItems] = useState<Prediction[]>([])
  const [open, setOpen] = useState(false)
  const [highlight, setHighlight] = useState(-1)
  const [plainAddress, setPlainAddress] = useState<string | null>(null)
  const debounceRef = useRef(0)
  const sessionTokenRef = useRef<any>(null)

  useEffect(() => {
    if (!apiKey || window.google?.maps?.places) {
      if (apiKey) setMapsReady(true)
      return
    }
    let cancelled = false
    loadGoogleMaps(apiKey)
      .then(() => !cancelled && setMapsReady(true))
      .catch(() => {
        /* the map panel will surface the load error */
      })
    return () => {
      cancelled = true
    }
  }, [apiKey])

  // No-Maps fallback: report the typed text verbatim as the address (no
  // coordinates are available without Places).
  useEffect(() => {
    if (plainAddress === null) return
    const selection: PlaceSelection = { address: plainAddress, name: '', lat: null, lng: null }
    onChange(selection)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [plainAddress])

  useEffect(() => () => window.clearTimeout(debounceRef.current), [])

  function nextSessionToken() {
    if (!sessionTokenRef.current) {
      sessionTokenRef.current = new window.google.maps.places.AutocompleteSessionToken()
    }
    return sessionTokenRef.current
  }

  function fetchPredictions(searchText: string) {
    window.clearTimeout(debounceRef.current)
    if (!mapsReady || !searchText.trim() || !window.google?.maps?.places) {
      setItems([])
      setOpen(false)
      return
    }
    debounceRef.current = window.setTimeout(() => {
      try {
        const service = new window.google.maps.places.AutocompleteService()
        service.getPredictions(
          { input: searchText, sessionToken: nextSessionToken() },
          (preds: any[] | null, status: string) => {
            if (status === 'OK' && preds && preds.length > 0) {
              setItems(
                preds.map((p) => ({
                  placeId: p.place_id,
                  main: p.structured_formatting?.main_text || p.description,
                  secondary: p.structured_formatting?.secondary_text || '',
                  desc: p.description,
                })),
              )
              setOpen(true)
              setHighlight(-1)
            } else {
              setItems([])
              setOpen(false)
            }
          },
        )
      } catch {
        /* Places unavailable (key restriction) — plain input fallback */
      }
    }, 220)
  }

  function setTyped(text: string) {
    if (inputRef.current) inputRef.current.value = text
  }

  function pick(item: Prediction) {
    setOpen(false)
    setItems([])
    try {
      // item.placeId is Google's own id from the prediction list above (never
      // raw user text). Details are fetched through a detached PlacesService,
      // so no visible map is required here.
      const placesService = new window.google.maps.places.PlacesService(document.createElement('div'))
      placesService.getDetails(
        { placeId: item.placeId, fields: PLACE_DETAIL_FIELDS, sessionToken: sessionTokenRef.current },
        (place: any, status: string) => {
          if (status === 'OK' && place?.geometry) {
            const selection: PlaceSelection = {
              address: place.formatted_address || item.desc,
              name: place.name || item.main,
              lat: place.geometry.location.lat(),
              lng: place.geometry.location.lng(),
            }
            setTyped(selection.address)
            onChange(selection)
          } else {
            const fallback: PlaceSelection = { address: item.desc, name: item.main, lat: null, lng: null }
            setTyped(fallback.address)
            onChange(fallback)
          }
        },
      )
    } catch {
      const fallback: PlaceSelection = { address: item.desc, name: item.main, lat: null, lng: null }
      setTyped(fallback.address)
      onChange(fallback)
    }
  }

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (!open || items.length === 0) return
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setHighlight((h) => (h + 1) % items.length)
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        setHighlight((h) => (h <= 0 ? items.length - 1 : h - 1))
      } else if (e.key === 'Enter') {
        e.preventDefault()
        pick(items[highlight >= 0 ? highlight : 0])
      } else if (e.key === 'Escape') {
        setOpen(false)
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [open, items, highlight],
  )

  return (
    <div className="relative">
      <input
        ref={inputRef}
        className="input"
        defaultValue={value}
        placeholder={placeholder || (mapsReady ? 'Search a place by name or address…' : 'Type an address')}
        onChange={(e) => {
          if (mapsReady) fetchPredictions(e.target.value)
          else setPlainAddress(e.target.value)
        }}
        onKeyDown={onKeyDown}
        onBlur={() => window.setTimeout(() => setOpen(false), 150)}
      />
      {open && items.length > 0 && (
        <ul
          className="absolute z-50 mt-1 max-h-60 w-full overflow-auto rounded-xl border border-slate-200 bg-white py-1 shadow-lg"
          role="listbox"
        >
          {items.map((it, i) => (
            <li key={it.placeId}>
              <button
                type="button"
                role="option"
                aria-selected={i === highlight}
                className={`block w-full px-3 py-1.5 text-left text-sm ${i === highlight ? 'bg-indigo-50' : 'hover:bg-slate-50'}`}
                onMouseDown={(e) => {
                  // keep keyboard focus in the input when clicking a choice
                  e.preventDefault()
                }}
                onClick={() => pick(it)}
                onMouseEnter={() => setHighlight(i)}
              >
                <span className="font-medium text-slate-800">{it.main}</span>
                {it.secondary && <span className="block text-xs text-slate-400">{it.secondary}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
