export type VenueType = 'food' | 'activity'
export type Level = 'yes' | 'weak' | 'strong'

export interface UserInfo {
  user_id: string
  display_name: string
  is_admin: boolean
}

export interface AppConfig {
  testing_mode: boolean
  okta_enabled: boolean
  maps_api_key: string
  /** Base URL for the MCP hints when the server was started with
   * --mcp-hostname/--mcp-port/--mcp-subpath; null = derive from address bar. */
  mcp_url_override: string | null
}

export interface Settings {
  event_title: string
  event_description: string
  budget_amount: number | null
  budget_type: 'per_head' | 'total'
  headcount_limit: number | null
  preference_mode: 'simple' | 'strong_weak'
  allow_venue_suggestions: boolean
  anonymous_voting: boolean
  hide_live_counts: boolean
  show_footer_to_voters: boolean
  voting_closes_at: string | null
  voting_closed: boolean
  office_address: string
  office_lat: number | null
  office_lng: number | null
  google_maps_api_key: string
}

export interface FooterEntry {
  date: string
  agent: string
  model: string
  work: string
  tokens_in: number
  tokens_out: number
  cost_usd: number
  estimated: boolean
}

export interface FooterData {
  repo_url: string
  built_by_ai: boolean
  entries: FooterEntry[]
  totals: { tokens_in?: number; tokens_out?: number; cost_usd?: number; estimated?: boolean }
  note?: string
}

export interface TimeSlot {
  id: number
  date: string // YYYY-MM-DD
  start_time: string // HH:MM
  end_time: string // HH:MM
}

export interface Venue {
  id: number
  name: string
  type: VenueType
  description: string
  estimated_cost: number | null
  address: string
  lat: number | null
  lng: number | null
  suggested_by: string | null
  suggester_name: string | null
  slot_ids: number[]
  active: boolean
}

export interface SlotCounts {
  yes: number
  weak: number
  strong: number
  total: number
}

export interface VenueResult {
  count: number
  voters?: string[]
}

export interface Results {
  visible: boolean
  reason: 'live' | 'closed' | 'hidden_until_close' | string
  availability: Record<string, SlotCounts>
  food: Record<string, VenueResult>
  activity: Record<string, VenueResult>
  voters: string[]
  headcount_taken: number
}

export interface AppState {
  authenticated: boolean
  server_time: string
  config: AppConfig
  settings: Settings
  status: { closed: boolean; reason: 'manual' | 'time' | null }
  slots: TimeSlot[]
  venues: Venue[]
  footer?: FooterData
  me?: UserInfo
  my_availability?: Record<string, string>
  my_vote?: { food_venue_ids: number[]; activity_venue_ids: number[]; has_vote: boolean }
  results?: Results
}

export interface AdminUserRow {
  user_id: string
  display_name: string
  is_admin: boolean
  created_at: string
  has_vote: boolean
}

export interface AdminVotes {
  anonymous: boolean
  closed: boolean
  slots: TimeSlot[]
  people: {
    user_id: string | null
    display_name: string
    has_vote: boolean
    availability: Record<string, string>
    food_venue_ids: number[]
    activity_venue_ids: number[]
  }[]
  results: Results
}
