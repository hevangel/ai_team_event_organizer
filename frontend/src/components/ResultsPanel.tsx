import type { AppState, Venue } from '../types'

function fmtDateTime(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString(undefined, { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

function venueStandings(venues: Venue[], resultMap: Record<string, { count: number; voters?: string[] }>) {
  return venues
    .map((v) => ({ venue: v, count: resultMap[String(v.id)]?.count ?? 0, voters: resultMap[String(v.id)]?.voters }))
    .sort((a, b) => b.count - a.count)
}

/** Sidebar: event status, my budget/headcount info, live or final results. */
export default function ResultsPanel({ state, draftDirty }: { state: AppState; draftDirty: boolean }) {
  const { settings, results, status, venues, slots } = state
  const namesAllowed = !settings.anonymous_voting

  return (
    <div className="space-y-4">
      <div className="card">
        <h3 className="mb-3 flex items-center justify-between text-sm font-bold text-slate-700">
          Event status
          {status.closed ? (
            <span className="chip bg-rose-100 text-rose-700">Voting closed</span>
          ) : (
            <span className="chip bg-emerald-100 text-emerald-700">Voting open</span>
          )}
        </h3>
        <dl className="space-y-1.5 text-sm">
          {settings.voting_closes_at && (
            <div className="flex justify-between gap-2">
              <dt className="text-slate-400">Closes</dt>
              <dd className="text-right font-medium text-slate-700">{fmtDateTime(settings.voting_closes_at)}</dd>
            </div>
          )}
          {settings.headcount_limit != null && results && (
            <div className="flex justify-between gap-2">
              <dt className="text-slate-400">Headcount</dt>
              <dd className="font-medium text-slate-700">
                {results.headcount_taken} / {settings.headcount_limit}
              </dd>
            </div>
          )}
          {settings.budget_amount != null && (
            <div className="flex justify-between gap-2">
              <dt className="text-slate-400">Budget</dt>
              <dd className="font-medium text-slate-700">
                ${settings.budget_amount} {settings.budget_type === 'per_head' ? 'per head' : 'total'}
              </dd>
            </div>
          )}
          {settings.office_address && (
            <div className="flex justify-between gap-2">
              <dt className="text-slate-400">Office</dt>
              <dd className="text-right font-medium text-slate-700">{settings.office_address}</dd>
            </div>
          )}
          <div className="flex justify-between gap-2">
            <dt className="text-slate-400">Votes</dt>
            <dd className="font-medium text-slate-700">
              {slots.length} slots · {venues.length} venues
            </dd>
          </div>
        </dl>
      </div>

      <div className="card">
        <h3 className="mb-3 flex items-center justify-between text-sm font-bold text-slate-700">
          {status.closed ? 'Final results' : 'Live results'}
          {!settings.anonymous_voting && namesAllowed && <span className="text-xs font-normal text-slate-400">names visible</span>}
          {settings.anonymous_voting && <span className="chip bg-slate-100 text-slate-500">anonymous</span>}
        </h3>

        {!results || !results.visible ? (
          <div className="rounded-xl bg-slate-50 px-4 py-6 text-center">
            <span className="text-2xl">🔒</span>
            <p className="mt-1 text-sm text-slate-500">Results are hidden until voting closes.</p>
          </div>
        ) : (
          <div className="space-y-4">
            {slots.length > 0 && (
              <div>
                <h4 className="mb-1.5 text-xs font-semibold tracking-wide text-slate-400 uppercase">Who's free when</h4>
                <div className="space-y-1">
                  {slots.map((s) => {
                    const c = results.availability[String(s.id)]
                    const total = c?.total ?? 0
                    return (
                      <div key={s.id} className="flex items-center gap-2 text-xs">
                        <span className="w-28 shrink-0 text-slate-500">
                          {new Date(s.date + 'T12:00:00').toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })}{' '}
                          {s.start_time}
                        </span>
                        <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
                          <div
                            className="h-full rounded-full bg-indigo-400 transition-all"
                            style={{ width: `${Math.min(100, total * 20)}%` }}
                          />
                        </div>
                        <span className="w-6 text-right font-semibold text-slate-600">{total}</span>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {(['food', 'activity'] as const).map((kind) => {
              const kindVenues = venues.filter((v) => v.type === kind)
              if (kindVenues.length === 0) return null
              const standings = venueStandings(kindVenues, kind === 'food' ? results.food : results.activity)
              return (
                <div key={kind}>
                  <h4 className="mb-1.5 text-xs font-semibold tracking-wide text-slate-400 uppercase">
                    {kind === 'food' ? '🍽 Food' : '🎯 Activity'}
                  </h4>
                  <div className="space-y-1">
                    {standings.map(({ venue, count, voters }) => (
                      <div key={venue.id} className="flex items-baseline justify-between gap-2 text-xs">
                        <span className={count > 0 ? 'font-medium text-slate-700' : 'text-slate-400'}>
                          {venue.name}
                          {namesAllowed && voters && voters.length > 0 && (
                            <span className="ml-1 font-normal text-slate-400">({voters.join(', ')})</span>
                          )}
                        </span>
                        <span className={`shrink-0 font-bold ${count > 0 ? 'text-indigo-600' : 'text-slate-300'}`}>{count}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )
            })}

            {namesAllowed && results.voters.length > 0 && (
              <p className="border-t border-slate-100 pt-2 text-xs text-slate-400">
                Voted so far: {results.voters.join(', ')}
              </p>
            )}
          </div>
        )}
      </div>

      {draftDirty && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-700">
          You have unsaved changes — hit <b>Save my vote</b> below.
        </div>
      )}
    </div>
  )
}
