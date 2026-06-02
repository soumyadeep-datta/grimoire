export interface ToolStatus {
  tool: string
  status: string
  done?: boolean
}

/**
 * A single ordered step in the agent's reasoning timeline.
 *
 * Unlike ToolStatus (which is keyed by tool name and overwrites), ToolStep is
 * append-only and ordered — so a sequence like rag → web → rag shows as three
 * distinct steps. Status text updates in place within the *current* step; a new
 * step is opened when the tool changes from the previous step.
 *
 * searchQuery preserves the initial "Searching: 'X'" text so the timeline
 * can show both what was searched and what was found.
 */
export interface ToolStep {
  id: string
  tool: string
  status: string
  searchQuery?: string   // preserved from the initial on_tool_start
  done: boolean
  order: number
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources?: string[]
  toolStatuses?: ToolStatus[]
  toolSteps?: ToolStep[]
  latencyMs?: number
  streaming?: boolean
  failed?: boolean
  originalQuery?: string
}

export interface Session {
  id: string
  label: string
  createdAt: Date
  lastMessage?: string
}

export interface StreamEvent {
  type: 'status' | 'token' | 'sources' | 'done' | 'error'
  data: Record<string, unknown>
}