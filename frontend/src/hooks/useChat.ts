import { useState, useCallback, useRef, useEffect } from 'react'
import { v4 as uuidv4 } from 'uuid'
import { Message, Session, ToolStatus, ToolStep } from '@/lib/types'
import { streamQuery, clearHistory, getHistory } from '@/lib/api'

// ── localStorage helpers ─────────────────────────────────────────────────────
// Sessions are persisted in the browser so the sidebar survives page reloads.
// The actual conversation content lives in the backend checkpoint store —
// localStorage only tracks which session IDs exist and their labels.

const STORAGE_KEY = 'grimoire-sessions'

function loadSessions(): Session[] {
  if (typeof window === 'undefined') return []
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return parsed.map((s: any) => ({
      ...s,
      createdAt: new Date(s.createdAt),
    }))
  } catch {
    return []
  }
}

function saveSessions(sessions: Session[]) {
  if (typeof window === 'undefined') return
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions))
  } catch {
    // localStorage full or unavailable — silently degrade
  }
}

// ── Inline source extraction ─────────────────────────────────────────────────

function extractInlineSources(text: string): string[] {
  const pattern = /\[Source:\s*([^,\]]+?)(?:,\s*Chunk\s*(\d+))?\]/gi
  const found = new Set<string>()
  let match
  while ((match = pattern.exec(text)) !== null) {
    const source = match[1].trim()
    const chunk = match[2]
    found.add(chunk ? `${source} (chunk ${chunk})` : source)
  }
  return Array.from(found)
}

// ── Hook ─────────────────────────────────────────────────────────────────────

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [sessions, setSessions] = useState<Session[]>(loadSessions)
  const [currentSessionId, setCurrentSessionId] = useState<string>(() => uuidv4())
  const [isStreaming, setIsStreaming] = useState(false)

  // AbortController ref — used to cancel in-flight SSE streams when the
  // user switches conversations or starts a new one mid-stream.
  const abortControllerRef = useRef<AbortController | null>(null)

  // Persist sessions to localStorage whenever they change
  useEffect(() => {
    saveSessions(sessions)
  }, [sessions])

  // Cancel any in-flight stream. Called before starting a new stream,
  // switching sessions, or creating a new conversation.
  const cancelStream = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }
    setIsStreaming(false)
  }, [])

  const sendMessage = useCallback(async (question: string) => {
    if (!question.trim() || isStreaming) return

    // Cancel any previous in-flight stream
    cancelStream()

    const userMsg: Message = {
      id: uuidv4(),
      role: 'user',
      content: question,
    }

    const assistantId = uuidv4()
    const assistantMsg: Message = {
      id: assistantId,
      role: 'assistant',
      content: '',
      thinking: '',
      thinkingDone: false,
      toolStatuses: [],
      toolSteps: [],
      streaming: true,
      originalQuery: question,
    }

    setMessages(prev => [...prev, userMsg, assistantMsg])
    setIsStreaming(true)

    // Create a fresh AbortController for this stream
    const controller = new AbortController()
    abortControllerRef.current = controller

    // Update session list
    setSessions(prev => {
      const exists = prev.find(s => s.id === currentSessionId)
      if (exists) {
        return prev.map(s =>
          s.id === currentSessionId ? { ...s, lastMessage: question } : s
        )
      }
      return [
        {
          id: currentSessionId,
          label: question.slice(0, 40) + (question.length > 40 ? '…' : ''),
          createdAt: new Date(),
          lastMessage: question,
        },
        ...prev,
      ]
    })

    try {
      await streamQuery(question, currentSessionId, {
        onThinking: (text) => {
          setMessages(prev =>
            prev.map(m =>
              m.id === assistantId
                ? { ...m, thinking: (m.thinking ?? '') + text }
                : m
            )
          )
        },
        onStatus: (tool, status, done, elapsedMs, metrics) => {
          setMessages(prev =>
            prev.map(m => {
              if (m.id !== assistantId) return m

              const thinkingDone = true

              // Keyed status array (compatibility)
              const existing = m.toolStatuses ?? []
              const idx = existing.findIndex(t => t.tool === tool)
              const updated: ToolStatus = { tool, status, done }
              const newStatuses = idx >= 0
                ? existing.map((t, i) => (i === idx ? updated : t))
                : [...existing, updated]

              // Ordered timeline steps
              const steps = m.toolSteps ?? []
              const last = steps[steps.length - 1]
              let newSteps: ToolStep[]
              if (last && last.tool === tool && !last.done) {
                newSteps = steps.map((s, i) =>
                  i === steps.length - 1
                    ? {
                        ...s,
                        status,
                        done: done ?? false,
                        elapsedMs: elapsedMs,
                        metrics: (metrics as ToolStep['metrics']) ?? s.metrics,
                      }
                    : s
                )
              } else {
                newSteps = [
                  ...steps,
                  {
                    id: `${assistantId}-step-${steps.length}`,
                    tool,
                    status,
                    searchQuery: status,
                    done: done ?? false,
                    order: steps.length,
                    elapsedMs: elapsedMs,
                    metrics: metrics as ToolStep['metrics'],
                  },
                ]
              }

              return { ...m, thinkingDone, toolStatuses: newStatuses, toolSteps: newSteps }
            })
          )
        },
        onToken: (text) => {
          setMessages(prev =>
            prev.map(m =>
              m.id === assistantId
                ? { ...m, content: m.content + text, thinkingDone: true }
                : m
            )
          )
        },
        onSources: (sources) => {
          setMessages(prev =>
            prev.map(m =>
              m.id === assistantId ? { ...m, sources } : m
            )
          )
        },
        onDone: (latencyMs) => {
          abortControllerRef.current = null
          setMessages(prev =>
            prev.map(m => {
              if (m.id !== assistantId) return m
              const closedSteps = (m.toolSteps ?? []).map(s => ({ ...s, done: true }))

              let finalSources = m.sources ?? []
              if (finalSources.length === 0) {
                finalSources = extractInlineSources(m.content)
              }

              let finalContent = m.content
              let finalThinking = m.thinking
              if (!finalContent && finalThinking) {
                finalContent = finalThinking
                finalThinking = ''
              }

              return {
                ...m,
                content: finalContent,
                thinking: finalThinking,
                thinkingDone: true,
                streaming: false,
                latencyMs,
                toolSteps: closedSteps,
                sources: finalSources,
              }
            })
          )
          setIsStreaming(false)
        },
        onError: (message) => {
          abortControllerRef.current = null
          setMessages(prev =>
            prev.map(m =>
              m.id === assistantId
                ? { ...m, content: message, streaming: false, failed: true, thinkingDone: true }
                : m
            )
          )
          setIsStreaming(false)
        },
      }, controller.signal)
    } catch (err) {
      // AbortError means we intentionally cancelled — don't show error
      if (err instanceof DOMException && err.name === 'AbortError') {
        // Stream was cancelled by user action (switching conversations).
        // Mark the message as not-streaming but don't show an error.
        setMessages(prev =>
          prev.map(m =>
            m.id === assistantId && m.streaming
              ? { ...m, streaming: false, thinkingDone: true }
              : m
          )
        )
        setIsStreaming(false)
        return
      }

      abortControllerRef.current = null
      setMessages(prev =>
        prev.map(m =>
          m.id === assistantId
            ? {
                ...m,
                content: 'Unable to reach the server. Please try again in a moment.',
                streaming: false,
                failed: true,
                thinkingDone: true,
              }
            : m
        )
      )
      setIsStreaming(false)
    }
  }, [currentSessionId, isStreaming, cancelStream])

  const retryMessage = useCallback((messageId: string) => {
    const msg = messages.find(m => m.id === messageId)
    if (!msg || !msg.originalQuery) return
    setMessages(prev => {
      const idx = prev.findIndex(m => m.id === messageId)
      if (idx < 1) return prev
      return prev.slice(0, idx - 1)
    })
    setTimeout(() => sendMessage(msg.originalQuery!), 50)
  }, [messages, sendMessage])

  const newSession = useCallback(() => {
    cancelStream()
    setCurrentSessionId(uuidv4())
    setMessages([])
  }, [cancelStream])

  const switchSession = useCallback(async (sessionId: string) => {
    cancelStream()
    setCurrentSessionId(sessionId)
    setMessages([])
    try {
      const history = await getHistory(sessionId)
      const loadedMessages: Message[] = history.map((m: { role: string; content: string; blocks?: any[] }) => {
        const blocks = m.blocks ?? []
        const hasBlocks = m.role === 'assistant' && blocks.length > 0

        if (!hasBlocks) {
          return {
            id: uuidv4(),
            role: m.role === 'user' ? 'user' as const : 'assistant' as const,
            content: m.content,
            streaming: false,
          }
        }

        // Reconstruct rich state from polymorphic blocks
        const thinking = blocks
          .filter((b: any) => b.type === 'thinking')
          .map((b: any) => b.text)
          .join('')

        const toolSteps: ToolStep[] = blocks
          .filter((b: any) => b.type === 'tool')
          .map((b: any, i: number) => ({
            id: `loaded-step-${i}`,
            tool: b.tool,
            status: b.status ?? 'Done',
            searchQuery: b.query ? `Searching: "${b.query}"` : undefined,
            done: true,
            order: i,
            elapsedMs: b.elapsed_ms,
            metrics: b.metrics,
          }))

        const sources = blocks
          .filter((b: any) => b.type === 'source')
          .map((b: any) => b.name)

        const latencyMs = blocks.find((b: any) => b.type === 'latency')?.ms

        return {
          id: uuidv4(),
          role: 'assistant' as const,
          content: m.content,
          thinking: thinking || undefined,
          thinkingDone: true,
          toolSteps: toolSteps.length > 0 ? toolSteps : undefined,
          sources: sources.length > 0 ? sources : undefined,
          latencyMs,
          streaming: false,
        }
      })
      setMessages(loadedMessages)
    } catch {
      // If history fetch fails, stay with empty messages
    }
  }, [cancelStream])

  const clearSession = useCallback(async () => {
    cancelStream()
    await clearHistory(currentSessionId)
    setMessages([])
    setSessions(prev => prev.filter(s => s.id !== currentSessionId))
  }, [currentSessionId, cancelStream])

  return {
    messages, sessions, currentSessionId, isStreaming,
    sendMessage, retryMessage, newSession, switchSession, clearSession,
  }
}