'use client'
import { useEffect, useRef, useState } from 'react'
import { Message } from '@/lib/types'
import { MessageBubble } from './MessageBubble'
import { getCollectionStats } from '@/lib/api'
import { GrimoireMark } from '@/components/icons/GrimoireMark'

interface ChatWindowProps {
  messages: Message[]
  onSendSuggestion?: (text: string) => void
  onRetry?: (messageId: string) => void
}

export function ChatWindow({ messages, onSendSuggestion, onRetry }: ChatWindowProps) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const [totalChunks, setTotalChunks] = useState<number | null>(null)

  useEffect(() => {
    getCollectionStats().then(stats => setTotalChunks(stats.total_chunks ?? 0))
  }, [messages.length])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // ===== EMPTY STATE =====
  if (messages.length === 0) {
    const noDocuments = totalChunks === 0

    return (
      <div style={{
        flex: 1,
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
        padding: '40px 24px',
        gap: '28px',
      }}>
        {/* Hero GrimoireMark — large, slow breathing glow */}
        <div style={{
          animation: 'grimoire-breathe-glow 7s cubic-bezier(0.45, 0, 0.55, 1) infinite',
          willChange: 'filter, transform',
        }}>
          <GrimoireMark size={120} variant="hero" />
        </div>

        {/* Title + subtitle */}
        <div style={{ textAlign: 'center', maxWidth: '440px' }}>
          <h2 style={{
            fontSize: '22px',
            fontWeight: 500,
            color: 'var(--grimoire-text-strong)',
            letterSpacing: '-0.5px',
            margin: '0 0 10px 0',
          }}>
            {noDocuments ? 'No documents yet' : 'Welcome to Grimoire'}
          </h2>
          <p style={{
            fontSize: '14px',
            color: 'var(--grimoire-muted)',
            lineHeight: '1.7',
            margin: 0,
            letterSpacing: '-0.1px',
          }}>
            {noDocuments
              ? 'Drop a file in the sidebar to get started.'
              : 'Your agentic knowledge assistant. Ask anything about your ingested documents.'
            }
          </p>
        </div>

        {/* Suggestion chips — shown only when documents exist */}
        {!noDocuments && (
          <div style={{
            display: 'flex', flexDirection: 'column',
            gap: '8px',
            width: '100%',
            maxWidth: '440px',
          }}>
            {[
              'How does authentication work in this codebase?',
              'Explain the main architecture and data flow',
              'What are the key configuration options?',
            ].map((suggestion, i) => (
              <div
                key={i}
                onClick={() => onSendSuggestion?.(suggestion)}
                style={{
                  padding: '12px 16px',
                  borderRadius: 'var(--grimoire-radius)',
                  border: '1px solid var(--grimoire-border)',
                  background: 'var(--grimoire-faint)',
                  fontSize: '13px',
                  color: 'var(--grimoire-muted)',
                  cursor: 'pointer',
                  transition: 'var(--grimoire-transition)',
                  letterSpacing: '-0.1px',
                }}
                onMouseEnter={e => {
                  const el = e.currentTarget
                  el.style.borderColor = 'rgba(201, 177, 135, 0.25)'
                  el.style.color = 'var(--grimoire-text-strong)'
                  el.style.background = 'rgba(201, 177, 135, 0.04)'
                }}
                onMouseLeave={e => {
                  const el = e.currentTarget
                  el.style.borderColor = 'var(--grimoire-border)'
                  el.style.color = 'var(--grimoire-muted)'
                  el.style.background = 'var(--grimoire-faint)'
                }}
              >
                {suggestion}
              </div>
            ))}
          </div>
        )}
      </div>
    )
  }

  // ===== MESSAGE LIST =====
  return (
    <div style={{
      flex: 1,
      overflowY: 'auto',
      padding: '32px 56px 8px',
    }}>
      {messages.map(msg => (
        <MessageBubble
          key={msg.id}
          message={msg}
          onRetry={onRetry}
        />
      ))}
      <div ref={bottomRef} />
    </div>
  )
}