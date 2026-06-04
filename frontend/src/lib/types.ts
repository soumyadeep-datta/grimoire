export interface ToolStatus {
  tool: string
  status: string
  done?: boolean
}

export interface ToolStep {
  id: string
  tool: string
  status: string
  searchQuery?: string
  done: boolean
  order: number
  elapsedMs?: number          // ms since stream started
  metrics?: {                 // enriched metrics from backend
    top_score?: number        // best similarity/reranker score
    chunks?: number           // number of chunks retrieved
  }
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources?: string[]
  toolStatuses?: ToolStatus[]
  toolSteps?: ToolStep[]
  thinking?: string
  thinkingDone?: boolean
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
  type: 'thinking' | 'status' | 'token' | 'sources' | 'done' | 'error'
  data: Record<string, unknown>
}