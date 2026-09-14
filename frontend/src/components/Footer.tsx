import type { FooterData } from '../types'

function GitHubIcon() {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true" className="h-4 w-4 fill-current">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
    </svg>
  )
}

function fmtTokens(n?: number): string {
  if (!n || n <= 0) return ''
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${Math.round(n / 1_000)}K`
  return String(n)
}

/**
 * AI attribution footer: repo link + which agent built this + tokens/cost
 * spent so far (from backend/app/footer.json, updated at every commit).
 */
export default function Footer({ footer }: { footer?: FooterData }) {
  if (!footer) return null
  const last = footer.entries?.[footer.entries.length - 1]
  const repoName = footer.repo_url?.replace(/^https?:\/\/[^/]+\//, '') || ''
  const tokens = (footer.totals?.tokens_in || 0) + (footer.totals?.tokens_out || 0)
  const cost = footer.totals?.cost_usd
  const approx = footer.totals?.estimated ? '~' : ''
  const title = footer.note || ''

  return (
    <footer className="mt-2 flex flex-wrap items-center justify-center gap-x-3 gap-y-1 border-t border-slate-200/80 pt-4 pb-2 text-xs text-slate-400" title={title}>
      {footer.repo_url && (
        <a
          href={footer.repo_url}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1.5 font-medium text-slate-500 transition-colors hover:text-indigo-600"
        >
          <GitHubIcon />
          {repoName}
        </a>
      )}
      {footer.built_by_ai && last && (
        <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="hidden sm:inline text-slate-300">|</span>
          <span>
            🤖 Built by <b className="font-semibold text-slate-500">{last.agent}</b>
            {last.model && ` (${last.model})`}
          </span>
          {tokens > 0 && (
            <span>
              {approx}
              {fmtTokens(tokens)} tokens
            </span>
          )}
          {cost != null && cost > 0 && (
            <span>
              {approx}${cost.toFixed(2)} spent so far
            </span>
          )}
        </span>
      )}
    </footer>
  )
}
