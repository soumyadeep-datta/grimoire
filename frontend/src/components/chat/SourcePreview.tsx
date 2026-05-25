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
          style={{
            position: 'fixed', inset: 0, zIndex: 100,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(6px)',
            padding: '40px 20px',
          }}
          onClick={onClose}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.96, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 8 }}
            transition={{ duration: 0.18 }}
            onClick={e => e.stopPropagation()}
            style={{
              background: 'var(--grimoire-surface)',
              border: '1px solid var(--grimoire-border)',
              borderRadius: '14px',
              maxWidth: '720px', width: '100%',
              maxHeight: '85vh',
              display: 'flex', flexDirection: 'column',
              boxShadow: '0 20px 60px rgba(0,0,0,0.5)',
            }}
          >
            {/* Header */}
            <div style={{
              padding: '16px 20px',
              borderBottom: '1px solid var(--grimoire-border)',
              display: 'flex', alignItems: 'center', gap: '12px',
            }}>
              <div style={{
                width: '32px', height: '32px', borderRadius: '8px',
                background: 'linear-gradient(135deg, rgba(139,92,246,0.2), rgba(236,72,153,0.2))',
                border: '1px solid var(--grimoire-border)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                flexShrink: 0,
              }}>
                <FileText size={15} style={{ color: 'var(--grimoire-violet)' }} />
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{
                  fontSize: '14px', fontWeight: 600,
                  color: 'var(--grimoire-text)',
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>
                  {source}
                </div>
                <div style={{ fontSize: '11px', color: 'var(--grimoire-muted)', marginTop: '2px' }}>
                  {chunks.length > 0 ? `${chunks.length} chunk${chunks.length > 1 ? 's' : ''}` : 'Source document'}
                </div>
              </div>
              <button
                onClick={onClose}
                style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  width: '28px', height: '28px', borderRadius: '6px',
                  border: '1px solid var(--grimoire-border)',
                  background: 'transparent', color: 'var(--grimoire-muted)',
                  cursor: 'pointer', transition: 'all 0.15s', flexShrink: 0,
                }}
                onMouseEnter={e => {
                  e.currentTarget.style.color = 'var(--grimoire-text)'
                  e.currentTarget.style.borderColor = 'var(--grimoire-border-hover)'
                }}
                onMouseLeave={e => {
                  e.currentTarget.style.color = 'var(--grimoire-muted)'
                  e.currentTarget.style.borderColor = 'var(--grimoire-border)'
                }}
              >
                <X size={14} />
              </button>
            </div>

            {/* Content */}
            <div style={{ flex: 1, overflow: 'auto', padding: '16px 20px' }}>
              {loading && (
                <div style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  padding: '40px 0', color: 'var(--grimoire-muted)',
                }}>
                  <Loader2 size={20} className="animate-spin" />
                </div>
              )}

              {error && (
                <div style={{
                  padding: '12px', borderRadius: '8px',
                  background: 'rgba(239,68,68,0.08)',
                  border: '1px solid rgba(239,68,68,0.2)',
                  color: '#fca5a5', fontSize: '13px',
                }}>
                  {error}
                </div>
              )}

              {!loading && !error && chunks.length === 0 && (
                <div style={{
                  textAlign: 'center', padding: '40px 0',
                  color: 'var(--grimoire-muted)', fontSize: '13px',
                }}>
                  No chunks found for this source
                </div>
              )}

              {!loading && chunks.length > 0 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  {chunks.map(chunk => (
                    <div key={chunk.chunk_index} style={{
                      padding: '12px 14px', borderRadius: '8px',
                      background: 'rgba(139,92,246,0.04)',
                      border: '1px solid var(--grimoire-border)',
                    }}>
                      <div style={{
                        display: 'flex', alignItems: 'center', gap: '8px',
                        marginBottom: '8px',
                      }}>
                        <span style={{
                          padding: '2px 8px', borderRadius: '4px',
                          background: 'rgba(139,92,246,0.12)',
                          color: 'var(--grimoire-violet-bright)',
                          fontSize: '10px', fontWeight: 500,
                          fontFamily: 'monospace',
                        }}>
                          chunk {chunk.chunk_index}
                        </span>
                      </div>
                      <pre style={{
                        margin: 0, fontSize: '12.5px', lineHeight: '1.6',
                        whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                        color: 'var(--grimoire-text)',
                        fontFamily: 'inherit',
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