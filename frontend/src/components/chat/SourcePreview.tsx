'use client'
import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, FileText, Loader2 } from 'lucide-react'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface SourcePreviewProps {
  source: string | null
  onClose: () => void
}

interface ChunkData {
  content: string
  chunk_index: number
  source: string
  score?: number
}

export function SourcePreview({ source, onClose }: SourcePreviewProps) {
  const [chunks, setChunks] = useState<ChunkData[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!source) return

    setLoading(true)
    setError(null)
    setChunks([])

    fetch(`${API_BASE}/collections/source/content?source=${encodeURIComponent(source)}`)
      .then(res => {
        if (!res.ok) throw new Error(`Failed to fetch: ${res.status}`)
        return res.json()
      })
      .then(data => setChunks(data.chunks ?? []))
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }, [source])

  return (
    <AnimatePresence>
      {source && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
          style={{
            position: 'fixed', inset: 0, zIndex: 100,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: 'rgba(0,0,0,0.7)',
            backdropFilter: 'blur(8px)',
            WebkitBackdropFilter: 'blur(8px)',
            padding: '40px 20px',
          }}
          onClick={onClose}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.96, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 8 }}
            transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
            onClick={e => e.stopPropagation()}
            style={{
              background: 'var(--grimoire-surface)',
              border: '1px solid var(--grimoire-border)',
              borderRadius: 'var(--grimoire-radius-lg)',
              maxWidth: '740px',
              width: '100%',
              maxHeight: '85vh',
              display: 'flex', flexDirection: 'column',
              boxShadow: 'var(--grimoire-shadow-depth)',
            }}
          >
            {/* Header */}
            <div style={{
              padding: '18px 22px',
              borderBottom: '1px solid var(--grimoire-border)',
              display: 'flex', alignItems: 'center', gap: '14px',
            }}>
              <div style={{
                width: '34px', height: '34px',
                borderRadius: 'var(--grimoire-radius-sm)',
                background: 'linear-gradient(135deg, var(--grimoire-gold), var(--grimoire-sage))',
                border: '1px solid rgba(255,250,235,0.06)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                flexShrink: 0,
                position: 'relative',
                overflow: 'hidden',
              }}>
                <div style={{
                  position: 'absolute', inset: 0,
                  background: 'radial-gradient(circle at 30% 30%, rgba(255,250,235,0.3), transparent 55%)',
                }} />
                <FileText
                  size={15}
                  strokeWidth={1.8}
                  style={{ color: '#2b2618', position: 'relative' }}
                />
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{
                  fontSize: '14px',
                  fontWeight: 500,
                  color: 'var(--grimoire-text-strong)',
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  letterSpacing: '-0.2px',
                }}>
                  {source}
                </div>
                <div style={{
                  fontSize: '11px',
                  color: 'var(--grimoire-muted-2)',
                  marginTop: '3px',
                  letterSpacing: '-0.1px',
                }}>
                  {chunks.length > 0
                    ? `${chunks.length} chunk${chunks.length > 1 ? 's' : ''}`
                    : 'Source document'}
                </div>
              </div>
              <button
                onClick={onClose}
                style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  width: '30px', height: '30px',
                  borderRadius: '7px',
                  border: '1px solid var(--grimoire-border)',
                  background: 'transparent',
                  color: 'var(--grimoire-muted)',
                  cursor: 'pointer',
                  transition: 'var(--grimoire-transition-fast)',
                  flexShrink: 0,
                }}
                onMouseEnter={e => {
                  e.currentTarget.style.color = 'var(--grimoire-text-strong)'
                  e.currentTarget.style.borderColor = 'var(--grimoire-border-hover)'
                }}
                onMouseLeave={e => {
                  e.currentTarget.style.color = 'var(--grimoire-muted)'
                  e.currentTarget.style.borderColor = 'var(--grimoire-border)'
                }}
              >
                <X size={14} strokeWidth={1.8} />
              </button>
            </div>

            {/* Content */}
            <div style={{ flex: 1, overflow: 'auto', padding: '18px 22px' }}>
              {loading && (
                <div style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  padding: '48px 0',
                  color: 'var(--grimoire-gold)',
                }}>
                  <Loader2 size={20} className="animate-spin" />
                </div>
              )}

              {error && (
                <div style={{
                  padding: '14px',
                  borderRadius: 'var(--grimoire-radius-sm)',
                  background: 'rgba(200, 123, 123, 0.08)',
                  border: '1px solid rgba(200, 123, 123, 0.2)',
                  color: 'var(--grimoire-error)',
                  fontSize: '13px',
                  letterSpacing: '-0.1px',
                }}>
                  {error}
                </div>
              )}

              {!loading && !error && chunks.length === 0 && (
                <div style={{
                  textAlign: 'center', padding: '48px 0',
                  color: 'var(--grimoire-muted-2)', fontSize: '13px',
                  letterSpacing: '-0.1px',
                }}>
                  No chunks found for this source
                </div>
              )}

              {!loading && chunks.length > 0 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                  {chunks.map(chunk => (
                    <div key={chunk.chunk_index} style={{
                      padding: '14px 16px',
                      borderRadius: 'var(--grimoire-radius)',
                      background: 'rgba(201, 177, 135, 0.03)',
                      border: '1px solid var(--grimoire-border)',
                    }}>
                      <div style={{
                        display: 'flex', alignItems: 'center', gap: '8px',
                        marginBottom: '10px',
                      }}>
                        <span style={{
                          padding: '3px 9px',
                          borderRadius: '5px',
                          background: 'rgba(201, 177, 135, 0.1)',
                          color: 'var(--grimoire-gold-bright)',
                          fontSize: '10px',
                          fontWeight: 500,
                          fontFamily: 'SF Mono, monospace',
                          letterSpacing: '0.3px',
                        }}>
                          chunk {chunk.chunk_index}
                        </span>
                      </div>
                      <pre style={{
                        margin: 0,
                        fontSize: '13px',
                        lineHeight: '1.75',
                        whiteSpace: 'pre-wrap',
                        wordBreak: 'break-word',
                        color: 'var(--grimoire-text)',
                        fontFamily: 'inherit',
                        letterSpacing: '-0.1px',
                      }}>
                        {chunk.content}
                      </pre>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}