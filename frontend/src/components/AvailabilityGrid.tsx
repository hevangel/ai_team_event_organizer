import type { Level, Results, TimeSlot } from '../types'

const LEVEL_CYCLE: Record<'simple' | 'strong_weak', (Level | null)[]> = {
  simple: [null, 'yes'],
  strong_weak: [null, 'strong', 'weak'],
}

const LEVEL_LABEL: Record<Level, string> = {
  yes: 'Available',
  strong: 'Strong preference',
  weak: 'Weak preference',
}

const LEVEL_CLASS: Record<Level, string> = {
  yes: 'slot-level-yes',
  weak: 'slot-level-weak',
  strong: 'slot-level-strong',
}

function nextLevel(current: Level | undefined, mode: 'simple' | 'strong_weak'): Level | null {
  const cycle = LEVEL_CYCLE[mode]
  const idx = cycle.indexOf(current ?? null)
  return cycle[(idx + 1) % cycle.length]
}

/**
 * Calendar-style availability picker: columns are dates, rows are time
 * ranges. Clicking a cell cycles its availability level. No checkboxes.
 */
export default function AvailabilityGrid({
  slots,
  draft,
  mode,
  results,
  readOnly,
  onChange,
}: {
  slots: TimeSlot[]
  draft: Record<number, Level>
  mode: 'simple' | 'strong_weak'
  results?: Results
  readOnly: boolean
  onChange: (slotId: number, level: Level | null) => void
}) {
  const dates = [...new Set(slots.map((s) => s.date))].sort()
  const times = [...new Set(slots.map((s) => `${s.start_time}-${s.end_time}`))].sort()
  const slotAt = (date: string, time: string) =>
    slots.find((s) => s.date === date && `${s.start_time}-${s.end_time}` === time)

  const showCounts = !!results?.visible

  if (slots.length === 0) {
    return (
      <div className="rounded-xl bg-slate-50 px-4 py-8 text-center text-sm text-slate-400">
        The organizer hasn't published date/time options yet.
      </div>
    )
  }

  const setAllForDate = (date: string, level: Level | null) => {
    slots.filter((s) => s.date === date).forEach((s) => onChange(s.id, level))
  }

  return (
    <div>
      <div className="overflow-x-auto pb-1">
        <table className="w-full min-w-[560px] border-separate border-spacing-1">
          <thead>
            <tr>
              <th className="w-24" />
              {dates.map((d) => {
                const dt = new Date(d + 'T12:00:00')
                const isToday = new Date().toISOString().slice(0, 10) === d
                return (
                  <th key={d} className="pb-1 text-center">
                    <div className={`text-xs font-semibold uppercase ${isToday ? 'text-indigo-600' : 'text-slate-500'}`}>
                      {dt.toLocaleDateString(undefined, { weekday: 'short' })}
                    </div>
                    <div className={`text-sm font-bold ${isToday ? 'text-indigo-600' : 'text-slate-700'}`}>
                      {dt.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                    </div>
                    {!readOnly && (
                      <div className="mt-0.5 flex justify-center gap-0.5">
                        <button
                          className="rounded px-1 text-[10px] text-slate-400 hover:bg-emerald-100 hover:text-emerald-600"
                          title={`Mark all ${LEVEL_LABEL.yes.toLowerCase()} on this date`}
                          onClick={() => setAllForDate(d, mode === 'strong_weak' ? 'strong' : 'yes')}
                        >
                          all
                        </button>
                        <button
                          className="rounded px-1 text-[10px] text-slate-400 hover:bg-slate-200 hover:text-slate-600"
                          title="Clear this date"
                          onClick={() => setAllForDate(d, null)}
                        >
                          none
                        </button>
                      </div>
                    )}
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody>
            {times.map((time) => {
              const [start, end] = time.split('-')
              return (
                <tr key={time}>
                  <td className="pr-2 text-right text-xs font-medium whitespace-nowrap text-slate-500">
                    {start}–{end}
                  </td>
                  {dates.map((d) => {
                    const slot = slotAt(d, time)
                    if (!slot)
                      return (
                        <td key={d}>
                          <div className="h-11 rounded-lg border border-dashed border-slate-100 bg-slate-50/50" />
                        </td>
                      )
                    const level = draft[slot.id]
                    const counts = showCounts ? results?.availability[String(slot.id)] : undefined
                    return (
                      <td key={d}>
                        <button
                          disabled={readOnly}
                          className={`slot-cell ${level ? LEVEL_CLASS[level] : ''}`}
                          title={`${d} ${time}${level ? ` — ${LEVEL_LABEL[level]}` : ''} (click to change)`}
                          onClick={() => onChange(slot.id, nextLevel(level, mode))}
                        >
                          {level && (
                            <span className="absolute inset-0 flex items-center justify-center text-sm font-semibold text-slate-700/80">
                              {level === 'strong' ? '★' : level === 'weak' ? '~' : '✓'}
                            </span>
                          )}
                          {counts && counts.total > 0 && (
                            <span className="absolute right-1 bottom-0.5 text-[10px] font-bold text-slate-500">
                              {counts.total}
                            </span>
                          )}
                        </button>
                      </td>
                    )
                  })}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-3.5 w-3.5 rounded border border-slate-300 bg-white" />
          not available
        </span>
        {mode === 'strong_weak' ? (
          <>
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-3.5 w-3.5 rounded border border-violet-500 bg-violet-300/70" />★
              strong preference
            </span>
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-3.5 w-3.5 rounded border border-amber-400 bg-amber-200/70" />~ weak
              preference
            </span>
          </>
        ) : (
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-3.5 w-3.5 rounded border border-emerald-400 bg-emerald-200/70" />✓
            available
          </span>
        )}
        {showCounts && <span className="ml-auto">corner number = people available</span>}
      </div>
    </div>
  )
}
