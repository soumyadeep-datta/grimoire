'use client'
import ReactMarkdown from 'react-markdown'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { Copy, Check, RefreshCw, AlertCircle } from 'lucide-react'
import { useState } from 'react'
import { motion } from 'framer-motion'
import { Message } from '@/lib/types'
import { ToolTrace } from './ToolTrace'
import { SourcePreview } from './SourcePreview'
import { GrimoireMark } from '@/components/icons/GrimoireMark'

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
        display: 'flex', alignItems: 'center', gap: '5px',
        padding: '4px 9px',
        borderRadius: '6px',
        border: '1px solid rgba(201, 177, 135, 0.18)',
        background: 'rgba(201, 177, 135, 0.06)',
        color: copied ? 'var(--grimoire-gold-bright)' : 'var(--grimoire-muted)',
        fontSize: '11px',
        cursor: 'pointer',
        transition: 'var(--grimoire-transition-fast)',
        fontFamily: 'inherit',
        letterSpacing: '-0.1px',
      }}
    >
      {copied ? <Check size={11} strokeWidth={2} /> : <Copy size={11} strokeWidth={1.8} />}
      {copied ? 'Copied' : 'Copy'}
    </button>
  )
}

export function MessageBubble({
  message,
  onRetry,
}: {
  message: Message
  onRetry?: (messageId: string) => void
}) {
  const isUser = message.role === 'user'
  const [selectedSource, setSelectedSource] = useState<string | null>(null)

  // ===== USER MESSAGE =====
  if (isUser) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.38, ease: [0.4, 0, 0.2, 1] }}
        style={{
          display: 'flex',
          justifyContent: 'flex-end',
          marginBottom: '28px',
        }}
      >
        <div style={{
          maxWidth: '68%',
          padding: '13px 18px',
          borderRadius: '20px 20px 4px 20px',
          background: 'linear-gradient(135deg, rgba(201,177,135,0.12) 0%, rgba(138,157,125,0.08) 100%)',
          border: '1px solid rgba(201,177,135,0.15)',
          color: 'var(--grimoire-gold-soft)',
          fontSize: '14px',
          lineHeight: '1.6',
          letterSpacing: '-0.1px',
          backdropFilter: 'blur(20px)',
          WebkitBackdropFilter: 'blur(20px)',
        }}>
          {message.content}
        </div>
      </motion.div>
    )
  }

  // ===== ASSISTANT MESSAGE =====
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.38, ease: [0.4, 0, 0.2, 1] }}
      style={{
        display: 'flex',
        gap: '18px',
        marginBottom: '32px',
        alignItems: 'flex-start',
      }}
    >
      {/* Avatar — gold/sage gradient tile with GrimoireMark */}
      <div style={{
        width: '38px', height: '38px',
        borderRadius: '11px',
        flexShrink: 0,
        background: 'linear-gradient(135deg, var(--grimoire-gold) 0%, var(--grimoire-gold-deep) 50%, #6b5840 100%)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        marginTop: '2px',
        position: 'relative',
        overflow: 'hidden',
        boxShadow: '0 6px 20px rgba(201, 177, 135, 0.2), 0 0 0 1px rgba(255,250,235,0.06)',
      }}>
        {/* Subtle inner highlight */}
        <div style={{
          position: 'absolute', inset: 0,
          background: 'radial-gradient(circle at 30% 30%, rgba(255,250,235,0.35), transparent 55%)',
        }} />
        <GrimoireMark size={22} tint="black" style={{ position: 'relative' }} />
      </div>

      <div style={{ flex: 1, minWidth: 0, paddingTop: '6px' }}>
        {/* Tool trace pill */}
        {message.toolStatuses && message.toolStatuses.length > 0 && (
          <ToolTrace tools={message.toolStatuses} />
        )}

        {/* Failed state with retry button */}
        {message.failed && (
          <div style={{
            display: 'flex',
            alignItems: 'flex-start',
            gap: '11px',
            padding: '13px 16px',
            borderRadius: 'var(--grimoire-radius)',
            background: 'rgba(200, 123, 123, 0.06)',
            border: '1px solid rgba(200, 123, 123, 0.2)',
            marginBottom: '10px',
          }}>
            <AlertCircle
              size={14}
              strokeWidth={1.8}
              style={{
                color: 'var(--grimoire-error)',
                flexShrink: 0,
                marginTop: '2px',
              }}
            />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{
                fontSize: '13px',
                color: 'var(--grimoire-error)',
                marginBottom: '10px',
                lineHeight: '1.6',
                letterSpacing: '-0.1px',
              }}>
                {message.content || 'Something went wrong.'}
              </div>
              {onRetry && message.originalQuery && (
                <button
                  onClick={() => onRetry(message.id)}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '6px',
                    padding: '6px 12px',
                    borderRadius: '7px',
                    border: '1px solid rgba(200, 123, 123, 0.3)',
                    background: 'rgba(200, 123, 123, 0.1)',
                    color: 'var(--grimoire-error)',
                    fontSize: '11.5px',
                    fontWeight: 500,
                    cursor: 'pointer',
                    transition: 'var(--grimoire-transition-fast)',
                    fontFamily: 'inherit',
                    letterSpacing: '-0.1px',
                  }}
                  onMouseEnter={e => {
                    e.currentTarget.style.background = 'rgba(200, 123, 123, 0.18)'
                  }}
                  onMouseLeave={e => {
                    e.currentTarget.style.background = 'rgba(200, 123, 123, 0.1)'
                  }}
                >
                  <RefreshCw size={11} strokeWidth={1.8} />
                  Retry
                </button>
              )}
            </div>
          </div>
        )}

        {/* Content — markdown body */}
        {!message.failed && (
          <div style={{
            fontSize: '14.5px',
            lineHeight: '1.85',
            color: 'var(--grimoire-text)',
            letterSpacing: '-0.1px',
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
                        background: 'rgba(201, 177, 135, 0.12)',
                        color: 'var(--grimoire-gold-bright)',
                        padding: '2px 7px',
                        borderRadius: '5px',
                        fontSize: '12.5px',
                        fontFamily: 'SF Mono, monospace',
                      }} {...props}>
                        {children}
                      </code>
                    )
                  }

                  return (
                    <div style={{
                      borderRadius: 'var(--grimoire-radius)',
                      overflow: 'hidden',
                      border: '1px solid var(--grimoire-border)',
                      margin: '14px 0',
                    }}>
                      <div style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        padding: '7px 14px',
                        background: 'rgba(201, 177, 135, 0.04)',
                        borderBottom: '1px solid var(--grimoire-border)',
                      }}>
                        <span style={{
                          fontSize: '11px',
                          color: 'var(--grimoire-muted)',
                          fontFamily: 'SF Mono, monospace',
                          letterSpacing: '0.3px',
                        }}>
                          {match?.[1] ?? 'code'}
                        </span>
                        <CopyButton code={code} />
                      </div>
                      <SyntaxHighlighter
                        style={oneDark}
                        language={match?.[1] ?? 'text'}
                        PreTag="div"
                        customStyle={{
                          margin: 0,
                          padding: '14px 16px',
                          background: '#0a0c0e',
                          fontSize: '12.5px',
                          lineHeight: '1.6',
                        }}
                      >
                        {code}
                      </SyntaxHighlighter>
                    </div>
                  )
                },
                p: ({ children }) => (
                  <p style={{ margin: '0 0 12px', lineHeight: '1.85' }}>{children}</p>
                ),
                ul: ({ children }) => (
                  <ul style={{ margin: '8px 0', paddingLeft: '22px' }}>{children}</ul>
                ),
                ol: ({ children }) => (
                  <ol style={{ margin: '8px 0', paddingLeft: '22px' }}>{children}</ol>
                ),
                li: ({ children }) => (
                  <li style={{ margin: '4px 0', lineHeight: '1.75' }}>{children}</li>
                ),
                h1: ({ children }) => (
                  <h1 style={{
                    fontSize: '18px', fontWeight: 600,
                    margin: '18px 0 10px',
                    color: 'var(--grimoire-gold-soft)',
                    letterSpacing: '-0.3px',
                  }}>{children}</h1>
                ),
                h2: ({ children }) => (
                  <h2 style={{
                    fontSize: '16px', fontWeight: 600,
                    margin: '16px 0 8px',
                    color: 'var(--grimoire-gold-soft)',
                    letterSpacing: '-0.2px',
                  }}>{children}</h2>
                ),
                h3: ({ children }) => (
                  <h3 style={{
                    fontSize: '14.5px', fontWeight: 600,
                    margin: '14px 0 6px',
                    color: 'var(--grimoire-text-strong)',
                  }}>{children}</h3>
                ),
                strong: ({ children }) => (
                  <strong style={{
                    fontWeight: 600,
                    color: 'var(--grimoire-text-strong)',
                  }}>{children}</strong>
                ),
                em: ({ children }) => (
                  <em style={{
                    fontStyle: 'normal',
                    color: 'var(--grimoire-sage-bright)',
                  }}>{children}</em>
                ),
                blockquote: ({ children }) => (
                  <blockquote style={{
                    borderLeft: '2px solid var(--grimoire-gold)',
                    paddingLeft: '14px',
                    margin: '12px 0',
                    color: 'var(--grimoire-muted)',
                    fontStyle: 'italic',
                  }}>{children}</blockquote>
                ),
                table: ({ children }) => (
                  <div style={{ overflowX: 'auto', margin: '14px 0' }}>
                    <table style={{
                      borderCollapse: 'collapse',
                      width: '100%',
                      fontSize: '13px',
                    }}>{children}</table>
                  </div>
                ),
                th: ({ children }) => (
                  <th style={{
                    padding: '9px 13px',
                    background: 'rgba(201, 177, 135, 0.06)',
                    borderBottom: '1px solid var(--grimoire-border)',
                    textAlign: 'left',
                    fontWeight: 500,
                    color: 'var(--grimoire-text-strong)',
                  }}>{children}</th>
                ),
                td: ({ children }) => (
                  <td style={{
                    padding: '9px 13px',
                    borderBottom: '1px solid var(--grimoire-border)',
                  }}>{children}</td>
                ),
                a: ({ children, href }) => (
                  <a
                    href={href}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      color: 'var(--grimoire-gold-bright)',
                      textDecoration: 'underline',
                      textDecorationColor: 'rgba(201, 177, 135, 0.4)',
                      textUnderlineOffset: '3px',
                    }}
                  >{children}</a>
                ),
              }}
            >
              {message.content}
            </ReactMarkdown>

            {/* Streaming cursor — gold tone */}
            {message.streaming && (
              <span style={{
                display: 'inline-block',
                width: '2px',
                height: '15px',
                background: 'var(--grimoire-gold)',
                marginLeft: '2px',
                animation: 'blink 1s step-end infinite',
                verticalAlign: 'text-bottom',
              }} />
            )}
          </div>
        )}

        {/* Sources */}
        {message.sources && message.sources.length > 0 && (
          <div style={{
            marginTop: '20px',
            display: 'flex',
            flexWrap: 'wrap',
            gap: '7px',
            alignItems: 'center',
          }}>
            <span style={{
              fontSize: '11px',
              color: 'var(--grimoire-muted-2)',
              marginRight: '4px',
              letterSpacing: '-0.1px',
            }}>
              Sources
            </span>
            {Array.from(new Set(message.sources.map(src => src.split(' (chunk')[0].trim()))).map((src, i) => {
              // Alternate gold and sage for variety
              const isGold = i % 2 === 0
              return (
                <button
                  key={i}
                  onClick={() => setSelectedSource(src)}
                  title={`View ${src}`}
                  style={{
                    padding: '5px 13px',
                    borderRadius: '999px',
                    fontSize: '11.5px',
                    background: isGold
                      ? 'rgba(201, 177, 135, 0.06)'
                      : 'rgba(138, 157, 125, 0.06)',
                    border: `1px solid ${isGold
                      ? 'rgba(201, 177, 135, 0.2)'
                      : 'rgba(138, 157, 125, 0.2)'}`,
                    color: isGold
                      ? 'var(--grimoire-gold-bright)'
                      : 'var(--grimoire-sage-bright)',
                    cursor: 'pointer',
                    transition: 'var(--grimoire-transition)',
                    fontFamily: 'inherit',
                    letterSpacing: '-0.1px',
                  }}
                  onMouseEnter={e => {
                    e.currentTarget.style.background = isGold
                      ? 'rgba(201, 177, 135, 0.12)'
                      : 'rgba(138, 157, 125, 0.12)'
                  }}
                  onMouseLeave={e => {
                    e.currentTarget.style.background = isGold
                      ? 'rgba(201, 177, 135, 0.06)'
                      : 'rgba(138, 157, 125, 0.06)'
                  }}
                >
                  {src}
                </button>
              )
            })}
          </div>
        )}

        {/* Source preview modal */}
        <SourcePreview source={selectedSource} onClose={() => setSelectedSource(null)} />

        {/* Latency — monospace, refined */}
        {message.latencyMs && !message.streaming && (
          <div style={{
            marginTop: '14px',
            fontSize: '10.5px',
            color: 'var(--grimoire-faint-text)',
            letterSpacing: '0.1px',
            fontFamily: 'SF Mono, monospace',
          }}>
            {(message.latencyMs / 1000).toFixed(1)}s
          </div>
        )}
      </div>
    </motion.div>
  )
}