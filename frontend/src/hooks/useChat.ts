import { useState, useCallback, useRef } from 'react'
import { v4 as uuidv4 } from 'uuid'
import { Message, Session, ToolStatus, ToolStep } from '@/lib/types'
import { streamQuery, clearHistory, getHistory } from '@/lib/api'

/**
 * Extract inline source citations from answer text.
 * The agent embeds citations like [Source: hw3_updated.pdf, Chunk 28] in its
 * responses. We parse these out so they show as clickable pills even if the
 * SSE sources event failed or was empty.
 */
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

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [sessions, setSessions] = useState<Session[]>([])
  const [currentSessionId, setCurrentSessionId] = useState<string>(() => uuidv4())
  const [isStreaming, setIsStreaming] = useState(false)
  const abortRef = useRef<boolean>(false)

  const sendMessage = useCallback(async (question: string) => {
    if (!question.trim() || isStreaming) return

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
      toolStatuses: [],
      toolSteps: [],
      streaming: true,
      originalQuery: question,
    }

    setMessages(prev => [...prev, userMsg, assistantMsg])
    setIsStreaming(true)
    abortRef.current = false

    setSessions(prev => {
      const exists = prev.find(s => s.id === currentSessionId)
      if (exists) {
        return prev.map(s =>
          s.id === currentSessionId
            ? { ...s, lastMessage: question }
            : s
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
        onStatus: (tool, status, done) => {
          setMessages(prev =>
            prev.map(m => {
              if (m.id !== assistantId) return m

              // --- Existing keyed status array (kept for compatibility) ---
              const existing = m.toolStatuses ?? []
              const idx = existing.findIndex(t => t.tool === tool)
              const updated: ToolStatus = { tool, status, done }
              const newStatuses =
                idx >= 0
                  ? existing.map((t, i) => (i === idx ? updated : t))
                  : [...existing, updated]

              // --- Ordered timeline steps (append-only) ---
              const steps = m.toolSteps ?? []
              const last = steps[steps.length - 1]
              let newSteps: ToolStep[]

              if (last && last.tool === tool && !last.done) {
                // Same active tool — update status, preserve searchQuery.
                // When transitioning to done, the status changes from
                // "Searching: 'X'" to "Found 5 chunks". We keep the
                // original searchQuery so the UI shows both.
                newSteps = steps.map((s, i) =>
                  i === steps.length - 1
                    ? { ...s, status, done: done ?? false }
                    : s
                )
              } else {
                // New tool or previous step finished — open a new step.
                // Save the initial status as searchQuery so it's preserved
                // when the step completes with a result count.
                newSteps = [
                  ...steps,
                  {
                    id: `${assistantId}-step-${steps.length}`,
                    tool,
                    status,
                    searchQuery: status,  // preserve the initial "Searching: 'X'"
                    done: done ?? false,
                    order: steps.length,
                  },
                ]
              }

              return { ...m, toolStatuses: newStatuses, toolSteps: newSteps }
            })
          )
        },
        onToken: (text) => {
          if (abortRef.current) return
          setMessages(prev =>
            prev.map(m =>
              m.id === assistantId
                ? { ...m, content: m.content + text }
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
          setMessages(prev =>
            prev.map(m => {
              if (m.id !== assistantId) return m
              const closedSteps = (m.toolSteps ?? []).map(s => ({ ...s, done: true }))

              let finalSources = m.sources ?? []
              if (finalSources.length === 0) {
                finalSources = extractInlineSources(m.content)
              }

              return {
                ...m,
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
          setMessages(prev =>
            prev.map(m =>
              m.id === assistantId
                ? { ...m, content: message, streaming: false, failed: true }
                : m
            )
          )
          setIsStreaming(false)
        },
      })
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : 'Connection failed'
      setMessages(prev =>
        prev.map(m =>
          m.id === assistantId
            ? {
                ...m,
                content: 'Unable to reach the server. Please try again in a moment.',
                streaming: false,
                failed: true,
              }
            : m
        )
      )
      setIsStreaming(false)
    }
  }, [currentSessionId, isStreaming])

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
    setCurrentSessionId(uuidv4())
    setMessages([])
  }, [])

  const switchSession = useCallback(async (sessionId: string) => {
    setCurrentSessionId(sessionId)
    setMessages([])
    try {
      const history = await getHistory(sessionId)
      const loadedMessages: Message[] = history.map((m: { role: string; content: string }) => ({
        id: uuidv4(),
        role: m.role === 'user' ? 'user' : 'assistant',
        content: m.content,
        streaming: false,
      }))
      setMessages(loadedMessages)
    } catch {
      // If history fetch fails, just stay with empty messages
    }
  }, [])

  const clearSession = useCallback(async () => {
    await clearHistory(currentSessionId)
    setMessages([])
    setSessions(prev => prev.filter(s => s.id !== currentSessionId))
  }, [currentSessionId])

  return {
    messages,
    sessions,
    currentSessionId,
    isStreaming,
    sendMessage,
    retryMessage,
    newSession,
    switchSession,
    clearSession,
  }
}