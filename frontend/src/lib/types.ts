export interface ToolStatus {
  tool: string
  status: string
  done?: boolean
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources?: string[]
  toolStatuses?: ToolStatus[]
  latencyMs?: number
  streaming?: boolean
  failed?: boolean
  originalQuery?: string  // for retrying failed messages
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