'use client'
import { useState, useEffect } from 'react'
import { Plus, MessageSquare, Trash2, BookOpen, Moon, Sun, AlertTriangle } from 'lucide-react'
import { Session } from '@/lib/types'
import { getCollectionStats } from '@/lib/api'
import { UploadPanel } from './UploadPanel'
import { HealthIndicator } from './HealthIndicator'

interface SidebarProps {
  sessions: Session[]
  currentSessionId: string
  onNewSession: () => void
  onSwitchSession: (id: string) => void
  onClearSession: () => void
  isDark: boolean
  onToggleTheme: () => void
}

function ConfirmDialog({ onConfirm, onCancel }: { onConfirm: () => void; onCancel: () => void }) {
  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 100,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)',
    }} onClick={onCancel}>
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: 'var(--grimoire-surface)',
          border: '1px solid var(--grimoire-border)',
          borderRadius: '14px', padding: '24px', width: '300px',
          display: 'flex', flexDirection: 'column', gap: '16px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <AlertTriangle size={18} style={{ color: '#f87171', flexShrink: 0 }} />
          <span style={{ fontSize: '14px', fontWeight: 600, color: 'var(--grimoire-text)' }}>
            Delete conversation?
          </span>
        </div>
        <p style={{ fontSize: '13px', color: 'var(--grimoire-muted)', margin: 0, lineHeight: '1.5' }}>
          This will permanently delete the conversation history. This cannot be undone.
        </p>
        <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
          <button
            onClick={onCancel}
            style={{
              padding: '7px 14px', borderRadius: '8px', fontSize: '13px',
              border: '1px solid var(--grimoire-border)',
              background: 'transparent', color: 'var(--grimoire-muted)',
              cursor: 'pointer',
            }}
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            style={{
              padding: '7px 14px', borderRadius: '8px', fontSize: '13px',
              border: 'none',
              background: 'rgba(239,68,68,0.15)', color: '#f87171',
              cursor: 'pointer',
            }}
          >
            Delete
          </button>
        </div>
      </div>
    </div>
  )
}

export function Sidebar({
  sessions, currentSessionId,
  onNewSession, onSwitchSession, onClearSession,
  isDark, onToggleTheme,
}: SidebarProps) {
  const [hoveredSession, setHoveredSession] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [totalChunks, setTotalChunks] = useState(0)
  const [uniqueSources, setUniqueSources] = useState<string[]>([])

  const refreshStats = async () => {
    const stats = await getCollectionStats()
    setTotalChunks(stats.total_chunks ?? 0)
    setUniqueSources(stats.unique_sources ?? [])
  }

  useEffect(() => {
    refreshStats()
    // Refresh stats every 30s in case of external changes
    const interval = setInterval(refreshStats, 30000)
    return () => clearInterval(interval)
  }, [])

  return (
    <>
      {confirmDelete && (
        <ConfirmDialog
          onConfirm={() => { onClearSession(); setConfirmDelete(false) }}
          onCancel={() => setConfirmDelete(false)}
        />
      )}

      <div style={{
        width: '240px', flexShrink: 0,
        display: 'flex', flexDirection: 'column',
        borderRight: '1px solid var(--grimoire-border)',
        background: 'var(--grimoire-deep)',
        height: '100vh',
      }}>
        {/* Logo */}
        <div style={{
          padding: '20px 16px 16px',
          borderBottom: '1px solid var(--grimoire-border)',
          display: 'flex', alignItems: 'center', gap: '10px',
        }}>
          <div style={{
            width: '30px', height: '30px', borderRadius: '8px',
            background: 'linear-gradient(135deg, #8b5cf6, #ec4899)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            flexShrink: 0,
          }}>
            <BookOpen size={15} color="#fff" />
          </div>
          <span style={{
            fontSize: '15px', fontWeight: 600,
            background: 'linear-gradient(135deg, #a78bfa, #ec4899)',
            WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
          }}>
            Grimoire
          </span>
        </div>

        {/* Upload panel */}
        <UploadPanel
          totalChunks={totalChunks}
          uniqueSources={uniqueSources}
          onIngestComplete={refreshStats}
        />

        {/* New chat button */}
        <div style={{ padding: '8px 12px' }}>
          <button
            onClick={onNewSession}
            style={{
              width: '100%', display: 'flex', alignItems: 'center', gap: '8px',
              padding: '9px 12px', borderRadius: '10px',
              border: '1px solid var(--grimoire-border)',
              background: 'transparent', color: 'var(--grimoire-text)',
              fontSize: '13px', cursor: 'pointer', transition: 'all 0.2s',
            }}
            onMouseEnter={e => {
              e.currentTarget.style.background = 'var(--grimoire-faint)'
              e.currentTarget.style.borderColor = 'var(--grimoire-border-hover)'
            }}
            onMouseLeave={e => {
              e.currentTarget.style.background = 'transparent'
              e.currentTarget.style.borderColor = 'var(--grimoire-border)'
            }}
          >
            <Plus size={14} />
            New conversation
          </button>
        </div>

        {/* Sessions */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '4px 8px' }}>
          {sessions.length === 0 ? (
            <p style={{ padding: '8px', fontSize: '12px', color: 'var(--grimoire-muted)' }}>
              No conversations yet
            </p>
          ) : (
            sessions.map(session => (
              <div
                key={session.id}
                onMouseEnter={() => setHoveredSession(session.id)}
                onMouseLeave={() => setHoveredSession(null)}
                style={{
                  display: 'flex', alignItems: 'center', gap: '8px',
                  padding: '8px 10px', borderRadius: '8px',
                  background: session.id === currentSessionId ? 'var(--grimoire-faint)' : 'transparent',
                  marginBottom: '2px', cursor: 'pointer',
                  transition: 'all 0.15s',
                }}
                onClick={() => onSwitchSession(session.id)}
                onMouseOver={e => {
                  if (session.id !== currentSessionId)
                    e.currentTarget.style.background = 'rgba(139,92,246,0.06)'
                }}
                onMouseOut={e => {
                  if (session.id !== currentSessionId)
                    e.currentTarget.style.background = 'transparent'
                }}
              >
                <MessageSquare size={13} style={{
                  color: session.id === currentSessionId ? 'var(--grimoire-violet)' : 'var(--grimoire-muted)',
                  flexShrink: 0, marginTop: '1px',
                }} />
                <span style={{
                  overflow: 'hidden', textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap', flex: 1,
                  fontSize: '13px',
                  color: session.id === currentSessionId ? 'var(--grimoire-text)' : 'var(--grimoire-muted)',
                }}>
                  {session.label}
                </span>
                {hoveredSession === session.id && (
                  <button
                    onClick={e => {
                      e.stopPropagation()
                      onSwitchSession(session.id)
                      setConfirmDelete(true)
                    }}
                    title="Delete conversation"
                    style={{
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      width: '20px', height: '20px', borderRadius: '5px',
                      border: 'none', background: 'transparent',
                      color: 'var(--grimoire-muted)', cursor: 'pointer',
                      flexShrink: 0, transition: 'all 0.15s',
                    }}
                    onMouseEnter={e => { e.currentTarget.style.color = '#f87171' }}
                    onMouseLeave={e => { e.currentTarget.style.color = 'var(--grimoire-muted)' }}
                  >
                    <Trash2 size={12} />
                  </button>
                )}
              </div>
            ))
          )}
        </div>

        {/* Bottom controls — health + theme toggle */}
        <div style={{
          padding: '12px',
          borderTop: '1px solid var(--grimoire-border)',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          gap: '8px',
        }}>
          <HealthIndicator />
          <button
            onClick={onToggleTheme}
            title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              width: '32px', height: '32px', borderRadius: '8px',
              border: '1px solid var(--grimoire-border)',
              background: 'transparent', color: 'var(--grimoire-muted)',
              cursor: 'pointer', transition: 'all 0.2s', flexShrink: 0,
            }}
            onMouseEnter={e => {
              e.currentTarget.style.borderColor = 'var(--grimoire-border-hover)'
              e.currentTarget.style.color = 'var(--grimoire-violet)'
            }}
            onMouseLeave={e => {
              e.currentTarget.style.borderColor = 'var(--grimoire-border)'
              e.currentTarget.style.color = 'var(--grimoire-muted)'
            }}
          >
            {isDark ? <Sun size={14} /> : <Moon size={14} />}
          </button>
        </div>
      </div>
    </>
  )
}