import { useState, useCallback, useRef } from 'react'
import { v4 as uuidv4 } from 'uuid'
import { Message, Session, ToolStatus } from '@/lib/types'
import { streamQuery, clearHistory, getHistory } from '@/lib/api'

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [sessions, setSessions] = useState<Session[]>([])
  const [currentSessionId, setCurrentSessionId] = useState<string>(() => uuidv4())
  const [isStreaming, setIsStreaming] = useState(false)
  const abortRef = useRef<boolean>(false)

  const sendMessage = useCallback(async (question: string) => {
    if (!question.trim() || isStreaming) return

    // Add user message
    const userMsg: Message = {
      id: uuidv4(),
      role: 'user',
      content: question,
    }

    // Add streaming assistant placeholder
    const assistantId = uuidv4()
    const assistantMsg: Message = {
      id: assistantId,
      role: 'assistant',
      content: '',
      toolStatuses: [],
      streaming: true,
    }

    setMessages(prev => [...prev, userMsg, assistantMsg])
    setIsStreaming(true)
    abortRef.current = false

    // Update session list
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
              const existing = m.toolStatuses ?? []
              const idx = existing.findIndex(t => t.tool === tool)
              const updated: ToolStatus = { tool, status, done }
              const newStatuses =
                idx >= 0
                  ? existing.map((t, i) => (i === idx ? updated : t))
                  : [...existing, updated]
              return { ...m, toolStatuses: newStatuses }
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
            prev.map(m =>
              m.id === assistantId
                ? { ...m, streaming: false, latencyMs }
                : m
            )
          )
          setIsStreaming(false)
        },
        onError: (message) => {
          setMessages(prev =>
            prev.map(m =>
              m.id === assistantId
                ? { ...m, content: `Error: ${message}`, streaming: false }
                : m
            )
          )
          setIsStreaming(false)
        },
      })
    } catch {
      setMessages(prev =>
        prev.map(m =>
          m.id === assistantId
            ? { ...m, content: 'Something went wrong. Please try again.', streaming: false }
            : m
        )
      )
      setIsStreaming(false)
    }
  }, [currentSessionId, isStreaming])

  const newSession = useCallback(() => {
    setCurrentSessionId(uuidv4())
    setMessages([])
  }, [])

  const switchSession = useCallback(async (sessionId: string) => {
    setCurrentSessionId(sessionId)
    setMessages([]) // clear UI immediately
    try {
      const history = await getHistory(sessionId)
      // Convert backend HistoryMessage format to frontend Message format
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
    newSession,
    switchSession,
    clearSession,
  }
}