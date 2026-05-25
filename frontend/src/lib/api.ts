const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export interface StreamCallbacks {
  onStatus: (tool: string, status: string, done?: boolean) => void
  onToken: (text: string) => void
  onSources: (sources: string[]) => void
  onDone: (latencyMs: number) => void
  onError: (message: string) => void
}

export async function streamQuery(
  question: string,
  sessionId: string,
  callbacks: StreamCallbacks
): Promise<void> {
  const response = await fetch(`${API_BASE}/query/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, session_id: sessionId, use_agent: true }),
  })

  if (!response.ok) {
    callbacks.onError(`Request failed: ${response.status}`)
    return
  }

  const reader = response.body?.getReader()
  if (!reader) {
    callbacks.onError('No response body')
    return
  }

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''

    let currentEvent = ''
    for (const line of lines) {
      if (line.startsWith('event: ')) {
        currentEvent = line.slice(7).trim()
      } else if (line.startsWith('data: ') && currentEvent) {
        try {
          const data = JSON.parse(line.slice(6))
          switch (currentEvent) {
            case 'status':
              callbacks.onStatus(data.tool, data.status, data.done)
              break
            case 'token':
              callbacks.onToken(data.text)
              break
            case 'sources':
              callbacks.onSources(data.sources ?? [])
              break
            case 'done':
              callbacks.onDone(data.latency_ms ?? 0)
              break
            case 'error':
              callbacks.onError(data.message ?? 'Unknown error')
              break
          }
          currentEvent = ''
        } catch {
          // ignore malformed SSE lines
        }
      }
    }
  }
}

export async function getHistory(sessionId: string) {
  const res = await fetch(`${API_BASE}/history?session_id=${sessionId}`)
  if (!res.ok) return []
  const data = await res.json()
  return data.messages ?? []
}

export async function clearHistory(sessionId: string) {
  await fetch(`${API_BASE}/history?session_id=${sessionId}`, { method: 'DELETE' })
}

export async function getCollectionStats() {
  const res = await fetch(`${API_BASE}/collections`)
  if (!res.ok) return { total_chunks: 0, unique_sources: [] }
  return res.json()
}

export async function deleteSource(source: string) {
  const res = await fetch(`${API_BASE}/collections/source?source=${encodeURIComponent(source)}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error(`Delete failed: ${res.status}`)
}