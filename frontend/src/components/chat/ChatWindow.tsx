'use client'
import { useEffect, useRef, useState } from 'react'
import { Message } from '@/lib/types'
import { MessageBubble } from './MessageBubble'
import { BookOpen, AlertCircle } from 'lucide-react'
import { getCollectionStats } from '@/lib/api'

interface ChatWindowProps {
  messages: Message[]
  isDark: boolean
  onSendSuggestion?: (text: string) => void
  onRetry?: (messageId: string) => void
}

export function ChatWindow({ messages, isDark, onSendSuggestion, onRetry }: ChatWindowProps) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const [totalChunks, setTotalChunks] = useState<number | null>(null)

  useEffect(() => {
    getCollectionStats().then(stats => setTotalChunks(stats.total_chunks ?? 0))
  }, [messages.length]) // re-check after messages change (ingest might have happened)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  if (messages.length === 0) {
    const noDocuments = totalChunks === 0

    return (
      <div style={{
        flex: 1, display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
        padding: '40px 24px', gap: '16px',
      }}>
        <div style={{
          width: '56px', height: '56px', borderRadius: '16px',
          background: noDocuments
            ? 'linear-gradient(135deg, rgba(245,158,11,0.2), rgba(239,68,68,0.2))'
            : 'linear-gradient(135deg, rgba(139,92,246,0.2), rgba(236,72,153,0.2))',
          border: `1px solid ${noDocuments ? 'rgba(245,158,11,0.3)' : 'var(--grimoire-border)'}`,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          {noDocuments
            ? <AlertCircle size={24} style={{ color: '#f59e0b' }} />
            : <BookOpen size={24} style={{ color: 'var(--grimoire-violet)' }} />
          }
        </div>

        <div style={{ textAlign: 'center' }}>
          <h2 style={{
            fontSize: '20px', fontWeight: 600, marginBottom: '8px',
            background: noDocuments
              ? 'linear-gradient(135deg, #f59e0b, #ef4444)'
              : 'linear-gradient(135deg, #a78bfa, #ec4899)',
            WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
          }}>
            {noDocuments ? 'No documents ingested' : 'Grimoire'}
          </h2>
          <p style={{ fontSize: '14px', color: 'var(--grimoire-muted)', maxWidth: '360px', lineHeight: '1.6' }}>
            {noDocuments
              ? 'Ingest your documentation first using the API. Run this in your terminal:'
              : 'Your agentic developer knowledge assistant. Ask anything about your ingested documentation.'
            }
          </p>
        </div>

        {noDocuments ? (
          <div style={{
            width: '100%', maxWidth: '480px',
            padding: '12px 16px', borderRadius: '10px',
            border: '1px solid rgba(245,158,11,0.2)',
            background: 'rgba(245,158,11,0.05)',
            fontFamily: 'monospace', fontSize: '12px',
            color: '#f59e0b', lineHeight: '1.8',
          }}>
            <div>curl -X POST http://localhost:8000/ingest \</div>
            <div style={{ paddingLeft: '16px' }}>-F &quot;file=@your_doc.md&quot;</div>
            <div style={{ marginTop: '8px', color: 'var(--grimoire-muted)', fontFamily: 'inherit', fontSize: '11px' }}>
              Or use POST /ingest/text for raw text. See /docs for full API.
            </div>
          </div>
        ) : (
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
        )}
      </div>
    )
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '24px 20px' }}>
      {messages.map(msg => (
        <MessageBubble key={msg.id} message={msg} isDark={isDark} onRetry={onRetry} />
      ))}
      <div ref={bottomRef} />
    </div>
  )
}