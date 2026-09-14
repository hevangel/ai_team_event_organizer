import { useEffect, type ReactNode } from 'react'

export function Modal({
  title,
  onClose,
  children,
  wide,
  tall,
}: {
  title: string
  onClose: () => void
  children: ReactNode
  wide?: boolean
  /** Stretch to (almost) the full screen height with a scrolling body. */
  tall?: boolean
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-40 flex items-start justify-center overflow-y-auto bg-slate-900/40 p-4 backdrop-blur-[2px]">
      <div
        className={`mt-6 mb-6 flex w-full flex-col rounded-2xl bg-white shadow-2xl sm:mt-10 sm:mb-10 ${
          wide ? 'max-w-4xl' : 'max-w-lg'
        } ${tall ? 'h-[calc(100vh-3rem)] sm:h-[calc(100vh-5rem)]' : ''}`}
      >
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3.5">
          <h2 className="text-base font-semibold text-slate-800">{title}</h2>
          <button onClick={onClose} className="btn-ghost !px-2 !py-1 text-lg leading-none" aria-label="Close">
            ×
          </button>
        </div>
        <div className={`${tall ? 'flex-1 overflow-y-auto' : ''} p-5`}>{children}</div>
      </div>
    </div>
  )
}

export function Toggle({
  checked,
  onChange,
  label,
  hint,
  disabled,
}: {
  checked: boolean
  onChange: (v: boolean) => void
  label: string
  hint?: string
  disabled?: boolean
}) {
  return (
    <label className={`flex items-start justify-between gap-3 py-2 ${disabled ? 'opacity-50' : ''}`}>
      <span>
        <span className="block text-sm font-medium text-slate-700">{label}</span>
        {hint && <span className="mt-0.5 block text-xs text-slate-400">{hint}</span>}
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={`relative mt-0.5 h-6 w-11 shrink-0 rounded-full transition-colors ${
          checked ? 'bg-indigo-600' : 'bg-slate-300'
        }`}
      >
        <span
          className={`absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${
            checked ? 'translate-x-5' : ''
          }`}
        />
      </button>
    </label>
  )
}

export function Toast({ message }: { message: string | null }) {
  if (!message) return null
  return (
    <div className="pointer-events-none fixed top-4 left-1/2 z-50 -translate-x-1/2 rounded-full bg-slate-900/90 px-4 py-2 text-sm font-medium text-white shadow-lg">
      {message}
    </div>
  )
}

declare global {
  interface Window {
    google?: any
  }
}

let mapsPromise: Promise<void> | null = null

/** Load the Google Maps JS API once (no-op resolves if it is already there).
 * Uses the classic synchronous bootstrap — with `loading=async` the
 * `google.maps.*` constructors are not available directly. */
export function loadGoogleMaps(apiKey: string): Promise<void> {
  if (window.google?.maps) return Promise.resolve()
  if (!mapsPromise) {
    mapsPromise = new Promise<void>((resolve, reject) => {
      const script = document.createElement('script')
      script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(apiKey)}&libraries=places&v=quarterly`
      script.async = true
      script.onload = () => {
        if (window.google?.maps) resolve()
        else reject(new Error('Google Maps loaded but the namespace is missing'))
      }
      script.onerror = () => reject(new Error('Failed to load Google Maps (check the API key)'))
      document.head.appendChild(script)
    })
  }
  return mapsPromise
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-10 text-sm text-slate-400">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-indigo-500" />
      {label || 'Loading…'}
    </div>
  )
}
