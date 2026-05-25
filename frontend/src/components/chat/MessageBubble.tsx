'use client'
import ReactMarkdown from 'react-markdown'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { Copy, Check, BookOpen, RefreshCw, AlertCircle } from 'lucide-react'
import { useState } from 'react'
import { motion } from 'framer-motion'
import { Message } from '@/lib/types'
import { ToolTrace } from './ToolTrace'
import { SourcePreview } from './SourcePreview'

function CopyButton({ code }: { code: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      onClick={() => {
        navigator.clipboard.writeText(code)
        setCopied(true)
        setTimeout(() => setCopied(false), 2000)
      }}
      style={{
        display: 'flex', alignItems: 'center', gap: '4px',
        padding: '3px 8px', borderRadius: '6px',
        border: '1px solid rgba(139,92,246,0.2)',
        background: 'rgba(139,92,246,0.08)',
        color: copied ? '#a78bfa' : '#64748b',
        fontSize: '11px', cursor: 'pointer', transition: 'all 0.15s',
      }}
    >
      {copied ? <Check size={11} /> : <Copy size={11} />}
      {copied ? 'Copied' : 'Copy'}
    </button>
  )
}

export function MessageBubble({
  message,
  isDark,
  onRetry,
}: {
  message: Message
  isDark: boolean
  onRetry?: (messageId: string) => void
}) {
  const isUser = message.role === 'user'
  const [selectedSource, setSelectedSource] = useState<string | null>(null)

  if (isUser) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '20px' }}
      >
        <div style={{
          maxWidth: '75%',
          padding: '12px 16px',
          borderRadius: '18px 18px 4px 18px',
          background: 'linear-gradient(135deg, #7c3aed, #6d28d9)',
          color: '#fff',
          fontSize: '14px',
          lineHeight: '1.6',
          boxShadow: '0 4px 20px rgba(139,92,246,0.25)',
        }}>
          {message.content}
        </div>
      </motion.div>
    )
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      style={{ display: 'flex', gap: '12px', marginBottom: '24px', alignItems: 'flex-start' }}
    >
      {/* Avatar */}
      <div style={{
        width: '28px', height: '28px', borderRadius: '8px', flexShrink: 0,
        background: 'linear-gradient(135deg, #8b5cf6, #ec4899)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        marginTop: '2px',
      }}>
        <BookOpen size={13} color="#fff" />
      </div>

      <div style={{ flex: 1, minWidth: 0 }}>
        {/* Tool trace */}
        {message.toolStatuses && message.toolStatuses.length > 0 && (
          <ToolTrace tools={message.toolStatuses} />
        )}

        {/* Failed state with retry button */}
        {message.failed && (
          <div style={{
            display: 'flex', alignItems: 'flex-start', gap: '10px',
            padding: '12px 14px', borderRadius: '10px',
            background: 'rgba(239,68,68,0.06)',
            border: '1px solid rgba(239,68,68,0.2)',
            marginBottom: '8px',
          }}>
            <AlertCircle size={14} style={{
              color: '#f87171', flexShrink: 0, marginTop: '2px',
            }} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: '13px', color: '#fca5a5', marginBottom: '8px', lineHeight: '1.5' }}>
                {message.content || 'Something went wrong.'}
              </div>
              {onRetry && message.originalQuery && (
                <button
                  onClick={() => onRetry(message.id)}
                  style={{
                    display: 'inline-flex', alignItems: 'center', gap: '5px',
                    padding: '5px 10px', borderRadius: '6px',
                    border: '1px solid rgba(239,68,68,0.3)',
                    background: 'rgba(239,68,68,0.1)',
                    color: '#fca5a5',
                    fontSize: '11px', fontWeight: 500,
                    cursor: 'pointer', transition: 'all 0.15s',
                  }}
                  onMouseEnter={e => {
                    e.currentTarget.style.background = 'rgba(239,68,68,0.18)'
                  }}
                  onMouseLeave={e => {
                    e.currentTarget.style.background = 'rgba(239,68,68,0.1)'
                  }}
                >
                  <RefreshCw size={11} />
                  Retry
                </button>
              )}
            </div>
          </div>
        )}

        {/* Content */}
        {!message.failed && <div style={{
          fontSize: '14px',
          lineHeight: '1.75',
          color: 'var(--grimoire-text)',
        }}>
          <ReactMarkdown
            components={{
              code({ node, className, children, ...props }: any) {
                const match = /language-(\w+)/.exec(className || '')
                const code = String(children).replace(/\n$/, '')
                const isInline = !match && !String(children).includes('\n')

                if (isInline) {
                  return (
                    <code style={{
                      background: 'rgba(139,92,246,0.12)',
                      color: '#a78bfa',
                      padding: '1px 6px',
                      borderRadius: '4px',
                      fontSize: '12.5px',
                      fontFamily: 'monospace',
                    }} {...props}>
                      {children}
                    </code>
                  )
                }

                return (
                  <div style={{
                    borderRadius: '10px',
                    overflow: 'hidden',
                    border: '1px solid var(--grimoire-border)',
                    margin: '12px 0',
                  }}>
                    <div style={{
                      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                      padding: '6px 12px',
                      background: 'rgba(139,92,246,0.06)',
                      borderBottom: '1px solid var(--grimoire-border)',
                    }}>
                      <span style={{ fontSize: '11px', color: 'var(--grimoire-muted)', fontFamily: 'monospace' }}>
                        {match?.[1] ?? 'code'}
                      </span>
                      <CopyButton code={code} />
                    </div>
                    <SyntaxHighlighter
                      style={isDark ? oneDark : oneLight}
                      language={match?.[1] ?? 'text'}
                      PreTag="div"
                      customStyle={{
                        margin: 0, padding: '14px 16px',
                        background: isDark ? '#0d0d1a' : '#fafaf9',
                        fontSize: '12.5px', lineHeight: '1.6',
                      }}
                    >
                      {code}
                    </SyntaxHighlighter>
                  </div>
                )
              },
              p: ({ children }) => <p style={{ margin: '0 0 10px', lineHeight: '1.75' }}>{children}</p>,
              ul: ({ children }) => <ul style={{ margin: '6px 0', paddingLeft: '20px' }}>{children}</ul>,
              ol: ({ children }) => <ol style={{ margin: '6px 0', paddingLeft: '20px' }}>{children}</ol>,
              li: ({ children }) => <li style={{ margin: '3px 0', lineHeight: '1.65' }}>{children}</li>,
              h1: ({ children }) => <h1 style={{ fontSize: '18px', fontWeight: 600, margin: '16px 0 8px', color: 'var(--grimoire-violet-bright)' }}>{children}</h1>,
              h2: ({ children }) => <h2 style={{ fontSize: '16px', fontWeight: 600, margin: '14px 0 6px', color: 'var(--grimoire-violet-bright)' }}>{children}</h2>,
              h3: ({ children }) => <h3 style={{ fontSize: '14px', fontWeight: 600, margin: '12px 0 4px' }}>{children}</h3>,
              strong: ({ children }) => <strong style={{ fontWeight: 600, color: 'var(--grimoire-text)' }}>{children}</strong>,
              blockquote: ({ children }) => (
                <blockquote style={{
                  borderLeft: '3px solid var(--grimoire-violet)',
                  paddingLeft: '12px', margin: '10px 0',
                  color: 'var(--grimoire-muted)', fontStyle: 'italic',
                }}>{children}</blockquote>
              ),
              table: ({ children }) => (
                <div style={{ overflowX: 'auto', margin: '12px 0' }}>
                  <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: '13px' }}>{children}</table>
                </div>
              ),
              th: ({ children }) => (
                <th style={{ padding: '8px 12px', background: 'rgba(139,92,246,0.08)', borderBottom: '1px solid var(--grimoire-border)', textAlign: 'left', fontWeight: 500 }}>{children}</th>
              ),
              td: ({ children }) => (
                <td style={{ padding: '8px 12px', borderBottom: '1px solid var(--grimoire-border)' }}>{children}</td>
              ),
            }}
          >
            {message.content}
          </ReactMarkdown>

          {/* Streaming cursor */}
          {message.streaming && (
            <span style={{
              display: 'inline-block', width: '2px', height: '14px',
              background: 'var(--grimoire-violet)', marginLeft: '2px',
              animation: 'blink 1s step-end infinite', verticalAlign: 'text-bottom',
            }} />
          )}
        </div>}

        {/* Sources */}
        {message.sources && message.sources.length > 0 && (
          <div style={{ marginTop: '12px', display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
            <span style={{ fontSize: '11px', color: 'var(--grimoire-muted)', alignSelf: 'center' }}>Sources:</span>
            {Array.from(new Set(message.sources.map(src => src.split(' (chunk')[0].trim()))).map((src, i) => (
              <button
                key={i}
                onClick={() => setSelectedSource(src)}
                title={`View ${src}`}
                style={{
                  padding: '3px 10px', borderRadius: '12px', fontSize: '11px',
                  background: 'rgba(139,92,246,0.08)',
                  border: '1px solid rgba(139,92,246,0.2)',
                  color: 'var(--grimoire-violet-bright)',
                  cursor: 'pointer', transition: 'all 0.15s',
                  fontFamily: 'inherit',
                }}
                onMouseEnter={e => {
                  e.currentTarget.style.background = 'rgba(139,92,246,0.15)'
                  e.currentTarget.style.borderColor = 'rgba(139,92,246,0.4)'
                }}
                onMouseLeave={e => {
                  e.currentTarget.style.background = 'rgba(139,92,246,0.08)'
                  e.currentTarget.style.borderColor = 'rgba(139,92,246,0.2)'
                }}
              >
                {src}
              </button>
            ))}
          </div>
        )}

        {/* Source preview modal */}
        <SourcePreview source={selectedSource} onClose={() => setSelectedSource(null)} />

        {/* Latency */}
        {message.latencyMs && !message.streaming && (
          <p style={{ marginTop: '8px', fontSize: '11px', color: 'var(--grimoire-muted)' }}>
            {(message.latencyMs / 1000).toFixed(1)}s
          </p>
        )}
      </div>
    </motion.div>
  )
}