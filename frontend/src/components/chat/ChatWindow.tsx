'use client'
import { useEffect, useRef } from 'react'
import { Message } from '@/lib/types'
import { MessageBubble } from './MessageBubble'
import { BookOpen } from 'lucide-react'

interface ChatWindowProps {
  messages: Message[]
  isDark: boolean
  onSendSuggestion?: (text: string) => void
}

export function ChatWindow({ messages, isDark, onSendSuggestion }: ChatWindowProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  if (messages.length === 0) {
    return (
      <div style={{
        flex: 1, display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
        padding: '40px 24px', gap: '16px',
      }}>
        <div style={{
          width: '56px', height: '56px', borderRadius: '16px',
          background: 'linear-gradient(135deg, rgba(139,92,246,0.2), rgba(236,72,153,0.2))',
          border: '1px solid var(--grimoire-border)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <BookOpen size={24} style={{ color: 'var(--grimoire-violet)' }} />
        </div>
        <div style={{ textAlign: 'center' }}>
          <h2 style={{
            fontSize: '20px', fontWeight: 600, marginBottom: '8px',
            background: 'linear-gradient(135deg, #a78bfa, #ec4899)',
            WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
          }}>
            Grimoire
          </h2>
          <p style={{ fontSize: '14px', color: 'var(--grimoire-muted)', maxWidth: '320px', lineHeight: '1.6' }}>
            Your agentic developer knowledge assistant. Ask anything about your ingested documentation.
          </p>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', width: '100%', maxWidth: '420px', marginTop: '8px' }}>
          {[
            'How does authentication work in this codebase?',
            'Explain the main architecture and data flow',
            'What are the key configuration options?',
          ].map((suggestion, i) => (
            <div key={i}
              onClick={() => onSendSuggestion?.(suggestion)}
              style={{
                padding: '10px 14px', borderRadius: '10px',
                border: '1px solid var(--grimoire-border)',
                background: 'var(--grimoire-faint)',
                fontSize: '13px', color: 'var(--grimoire-muted)',
                cursor: 'pointer', transition: 'all 0.2s',
              }}
              onMouseEnter={e => {
                const el = e.currentTarget
                el.style.borderColor = 'var(--grimoire-border-hover)'
                el.style.color = 'var(--grimoire-text)'
                el.style.background = 'rgba(139,92,246,0.08)'
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
      </div>
    )
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '24px 20px' }}>
      {messages.map(msg => (
        <MessageBubble key={msg.id} message={msg} isDark={isDark} />
      ))}
      <div ref={bottomRef} />
    </div>
  )
}