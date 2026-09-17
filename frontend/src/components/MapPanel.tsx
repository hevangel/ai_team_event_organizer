import { useEffect, useMemo, useRef, useState } from 'react'
import { loadGoogleMaps } from './ui'
import type { Venue } from '../types'

const DEFAULT_CENTER = { lat: 37.7749, lng: -122.4194 }

function venueColor(v: Venue): string {
  return v.type === 'food' ? '#f97316' : '#0ea5e9'
}

function venueGlyph(v: Venue): string {
  return v.type === 'food' ? '🍽' : '🎯'
}

function markerIcon(color: string) {
  return {
    path: 'M -14 0 A 14 14 0 1 0 14 0 A 14 14 0 1 0 -14 0 M 0 -7 L 0 7 M -7 0 L 7 0',
    fillColor: color,
    fillOpacity: 1,
    strokeColor: 'white',
    strokeWeight: 2,
    scale: 0.9,
    labelOrigin: new window.google.maps.Point(0, 0),
  }
}

/**
 * InfoWindow content built from DOM nodes, never an HTML string: venue names
 * and descriptions are user-supplied (voters can suggest venues), so markup
 * in them must never be parsed as HTML.
 */
function infoContent(v: Venue): HTMLElement {
  const root = document.createElement('div')
  root.className = 'text-sm leading-snug'

  const title = document.createElement('b')
  title.textContent = v.name
  root.append(title)

  const lines: string[] = [v.type === 'food' ? '🍽 Food' : '🎯 Activity']
  if (v.estimated_cost != null) lines.push(`~$${v.estimated_cost}`)
  if (v.description) lines.push(v.description)

  for (const line of lines) {
    root.append(document.createElement('br'))
    root.append(document.createTextNode(line))
  }
  return root
}

/**
 * Google Maps wrapper. Shows the office + venue markers; highlights a venue
 * on hover; optionally lets the user click the map to pick coordinates.
 * Degrades to a placeholder panel when no API key is configured.
 */
export default function MapPanel({
  apiKey,
  center,
  venues,
  fallbackCenter,
  highlightId,
  pickMode,
  onPick,
  className,
}: {
  apiKey: string
  /** Office location: drawn with a 🏢 marker and included in the framing. */
  center: { lat: number; lng: number } | null
  venues: Venue[]
  /** Initial map center when there is no office pin (e.g. the suggest form before a search). */
  fallbackCenter?: { lat: number; lng: number } | null
  /** Venue to spotlight (list hover). Bounces the marker and opens its info card. */
  highlightId?: number | null
  pickMode?: boolean
  onPick?: (p: { lat: number; lng: number }) => void
  className?: string
}) {
  const divRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<any>(null)
  const markersRef = useRef<any[]>([])
  const byIdRef = useRef<Map<number, any>>(new Map())
  const highlightRef = useRef<{ marker: any; info: any } | null>(null)
  const pickMarkerRef = useRef<any>(null)
  const [ready, setReady] = useState(false)
  const [failed, setFailed] = useState<string | null>(null)

  // Rebuild markers only when the pins or the text they show actually change,
  // so periodic state polling never resets the user's pan/zoom — but an edited
  // venue name/description/cost does refresh its info card.
  const markerKey = useMemo(
    () =>
      (center ? `office@${center.lat.toFixed(6)},${center.lng.toFixed(6)}|` : '') +
      venues
        .map((v) =>
          [v.id, v.lat ?? '', v.lng ?? '', v.type, v.name, v.estimated_cost ?? '', v.description].join('~'),
        )
        .join('|'),
    [center, venues],
  )

  useEffect(() => {
    if (!apiKey) return
    let cancelled = false
    loadGoogleMaps(apiKey)
      .then(() => !cancelled && setReady(true))
      .catch((e) => !cancelled && setFailed(e instanceof Error ? e.message : 'Failed to load Google Maps'))
    return () => {
      cancelled = true
    }
  }, [apiKey])

  // Detach everything when the panel goes away so repeated modal opens /
  // tab switches don't leak map objects.
  useEffect(
    () => () => {
      markersRef.current.forEach((m) => m.setMap(null))
      markersRef.current = []
      byIdRef.current = new Map()
      highlightRef.current = null
      pickMarkerRef.current = null
      mapRef.current = null
    },
    [],
  )

  // Create the map once. A maps failure must never crash the app (an
  // uncaught effect error unmounts the whole React tree), so degrade to the
  // inline error box instead.
  useEffect(() => {
    if (!ready || !divRef.current || mapRef.current) return
    try {
      const firstVenue = venues.find((v) => v.lat != null && v.lng != null)
      const c =
        center ||
        fallbackCenter ||
        (firstVenue ? { lat: firstVenue.lat!, lng: firstVenue.lng! } : DEFAULT_CENTER)
      mapRef.current = new window.google.maps.Map(divRef.current, {
        center: c,
        zoom: 13,
        mapTypeControl: false,
        streetViewControl: false,
        clickableIcons: false,
      })
    } catch (e) {
      setFailed(e instanceof Error ? e.message : 'Google Maps failed to initialize')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, markerKey])

  // Sync venue markers + the office marker.
  useEffect(() => {
    if (!ready || !mapRef.current) return
    try {
      markersRef.current.forEach((m) => m.setMap(null))
      markersRef.current = []
      byIdRef.current = new Map()

      const points: { lat: number; lng: number }[] = []

      if (center) {
        const officeMarker = new window.google.maps.Marker({
          position: center,
          map: mapRef.current,
          title: 'Office',
          label: { text: '🏢', fontSize: '20px' },
        })
        markersRef.current.push(officeMarker)
        points.push(center)
      }

      for (const v of venues) {
        if (v.lat == null || v.lng == null) continue
        const m = new window.google.maps.Marker({
          position: { lat: v.lat, lng: v.lng },
          map: mapRef.current,
          title: v.name,
          icon: markerIcon(venueColor(v)),
          label: { text: venueGlyph(v), fontSize: '12px' },
        })
        m.addListener('click', () => {
          new window.google.maps.InfoWindow({ content: infoContent(v) }).open({ anchor: m, map: mapRef.current })
        })
        byIdRef.current.set(v.id, m)
        markersRef.current.push(m)
        points.push({ lat: v.lat, lng: v.lng })
      }

      // A single pin can't frame — center on it instead (fitBounds with a
      // zero-area bounds is ignored by Google Maps and strands the view).
      if (points.length === 1) {
        mapRef.current.setCenter(points[0])
        mapRef.current.setZoom(14)
      } else if (points.length > 1) {
        const bounds = new window.google.maps.LatLngBounds()
        points.forEach((p) => bounds.extend(p))
        mapRef.current.fitBounds(bounds, 60)
      }
    } catch (e) {
      setFailed(e instanceof Error ? e.message : 'Google Maps markers failed')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, markerKey])

  // Hover spotlight: bounce the marker + show its info card.
  useEffect(() => {
    if (!ready || !mapRef.current) return
    try {
      if (highlightRef.current) {
        highlightRef.current.marker.setAnimation(null)
        highlightRef.current.info.close()
        highlightRef.current = null
      }
      if (highlightId == null) return
      const marker = byIdRef.current.get(highlightId)
      const venue = venues.find((v) => v.id === highlightId)
      if (!marker || !venue) return
      marker.setAnimation(window.google.maps.Animation.BOUNCE)
      const info = new window.google.maps.InfoWindow({ content: infoContent(venue) })
      info.open({ anchor: marker, map: mapRef.current })
      mapRef.current.panTo(marker.getPosition())
      highlightRef.current = { marker, info }
    } catch {
      /* highlighting is decorative — never break the page over it */
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, highlightId, markerKey])

  // Click-to-pick mode.
  useEffect(() => {
    if (!ready || !mapRef.current || !pickMode) return
    try {
      const listener = mapRef.current.addListener('click', (e: any) => {
        if (!e.latLng) return
        const pos = { lat: e.latLng.lat(), lng: e.latLng.lng() }
        if (pickMarkerRef.current) pickMarkerRef.current.setMap(null)
        pickMarkerRef.current = new window.google.maps.Marker({
          position: pos,
          map: mapRef.current,
          label: { text: '📍', fontSize: '20px' },
        })
        onPick?.(pos)
      })
      return () => listener.remove()
    } catch {
      /* pick mode is best-effort */
    }
  }, [ready, pickMode, onPick])

  if (!apiKey) {
    return (
      <div className={`flex flex-col items-center justify-center rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-6 text-center ${className || ''}`}>
        <span className="text-3xl">🗺️</span>
        <p className="mt-2 max-w-xs text-sm text-slate-500">
          Google Maps isn't configured. The admin can add a Google Maps API key in the admin
          panel; venues can still be added by address.
        </p>
      </div>
    )
  }

  if (failed) {
    return (
      <div className={`flex items-center justify-center rounded-2xl bg-rose-50 p-6 text-sm text-rose-600 ${className || ''}`}>
        Google Maps problem: {failed}
      </div>
    )
  }

  return (
    <div className={`relative overflow-hidden rounded-2xl border border-slate-200 ${className || ''}`}>
      <div ref={divRef} className="h-full min-h-[280px] w-full" />
      {!ready && (
        <div className="absolute inset-0 flex items-center justify-center bg-slate-50 text-sm text-slate-400">
          Loading map…
        </div>
      )}
      {pickMode && ready && (
        <div className="pointer-events-none absolute top-3 left-1/2 -translate-x-1/2 rounded-full bg-indigo-600/90 px-3 py-1 text-xs font-medium text-white shadow">
          Click the map to drop a pin
        </div>
      )}
    </div>
  )
}
