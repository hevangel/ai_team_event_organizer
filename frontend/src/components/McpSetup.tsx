import { useState } from 'react'
import type { AppConfig } from '../types'

function mcpUrl(config: AppConfig): string {
  const base = config.mcp_url_override?.replace(/\/+$/, '') || window.location.origin
  return `${base}/mcp`
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      type="button"
      className="btn-ghost shrink-0 !rounded-lg !px-2 !py-1 text-xs"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text)
          setCopied(true)
          setTimeout(() => setCopied(false), 1500)
        } catch {
          /* clipboard unavailable (insecure context) */
        }
      }}
    >
      {copied ? '✓ copied' : 'copy'}
    </button>
  )
}

function CommandRow({ label, command }: { label: string; command: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-24 shrink-0 text-right text-xs font-semibold text-slate-500">{label}</span>
      <code className="min-w-0 flex-1 overflow-x-auto rounded-lg bg-slate-100 px-2.5 py-1.5 font-mono text-xs whitespace-nowrap text-slate-700">
        {command}
      </code>
      <CopyButton text={command} />
    </div>
  )
}

/** Login-page hints for connecting an AI agent (Claude Code / Codex) via MCP. */
export default function McpSetup({ config }: { config: AppConfig }) {
  const url = mcpUrl(config)
  return (
    <div className="card mt-4 !p-5">
      <h2 className="text-sm font-bold text-slate-700">🤖 Or let your AI agent vote for you</h2>
      <p className="mt-1 text-xs text-slate-400">
        Connect your agent once, then just tell it what you want — “I'm good Mon/Wed, never after
        3pm, vote sushi” — along with your userid.
      </p>
      <div className="mt-3 space-y-2">
        <CommandRow label="Claude Code" command={`claude mcp add --transport http team-event ${url}`} />
        <CommandRow label="Codex CLI" command={`codex mcp add team-event --url ${url}`} />
        <div className="flex items-center gap-2">
          <span className="w-24 shrink-0 text-right text-xs font-semibold text-slate-500">MCP URL</span>
          <a
            href={url}
            target="_blank"
            rel="noreferrer"
            className="min-w-0 flex-1 truncate font-mono text-xs text-indigo-600 hover:underline"
          >
            {url}
          </a>
          <CopyButton text={url} />
        </div>
      </div>
      <p className="mt-3 text-[11px] leading-relaxed text-slate-400">
        Codex can also be configured in <code>~/.codex/config.toml</code>:{' '}
        <code className="rounded bg-slate-100 px-1 py-0.5 font-mono">
          [mcp_servers.team-event] url = "{url}"
        </code>
        . Every tool takes a <code>user_id</code> — your agent votes as you.
      </p>
      {config.testing_mode ? (
        <p className="mt-2 text-[11px] leading-relaxed text-slate-400">
          Testing mode: the <code>user_id</code> is taken at face value, same trust rules as the
          userid login above.
        </p>
      ) : (
        <p className="mt-2 rounded-lg bg-amber-50 px-2.5 py-2 text-[11px] leading-relaxed text-amber-700">
          🔐 SSO is on, so a userid alone isn't enough: sign in here first, then give your agent
          your session token as a bearer header — e.g.{' '}
          <code className="rounded bg-amber-100/70 px-1 py-0.5 font-mono">
            claude mcp add --transport http --header "Authorization: Bearer $TEAM_EVENT_TOKEN"
            team-event {url}
          </code>
          . The server rejects calls whose session doesn't match the submitted{' '}
          <code>user_id</code>.
        </p>
      )}
    </div>
  )
}
