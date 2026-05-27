'use client'
import { useState, useEffect } from 'react'
import { Plus, MessageSquare, Trash2, AlertTriangle } from 'lucide-react'
import { Session } from '@/lib/types'
import { getCollectionStats } from '@/lib/api'
import { useConnection } from '@/lib/connection'
import { useToast } from '@/lib/toast'
import { UploadPanel } from './UploadPanel'
import { HealthIndicator } from './HealthIndicator'
import { GrimoireMark } from '@/components/icons/GrimoireMark'

interface SidebarProps {
  sessions: Session[]
  currentSessionId: string
  onNewSession: () => void
  onSwitchSession: (id: string) => void
  onClearSession: () => void
}

function ConfirmDialog({ onConfirm, onCancel }: { onConfirm: () => void; onCancel: () => void }) {
  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 100,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(8px)',
      }}
      onClick={onCancel}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: 'var(--grimoire-surface)',
          border: '1px solid var(--grimoire-border)',
          borderRadius: 'var(--grimoire-radius-lg)',
          padding: '24px', width: '320px',
          display: 'flex', flexDirection: 'column', gap: '16px',
          boxShadow: 'var(--grimoire-shadow-depth)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <AlertTriangle size={18} style={{ color: 'var(--grimoire-error)', flexShrink: 0 }} />
          <span style={{ fontSize: '14px', fontWeight: 500, color: 'var(--grimoire-text-strong)' }}>
            Delete conversation?
          </span>
        </div>
        <p style={{
          fontSize: '13px', color: 'var(--grimoire-muted)',
          margin: 0, lineHeight: '1.6',
        }}>
          This will permanently delete the conversation history. This cannot be undone.
        </p>
        <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
          <button
            onClick={onCancel}
            style={{
              padding: '8px 14px', borderRadius: 'var(--grimoire-radius-sm)', fontSize: '13px',
              border: '1px solid var(--grimoire-border)',
              background: 'transparent', color: 'var(--grimoire-muted)',
              cursor: 'pointer', transition: 'var(--grimoire-transition)',
              fontFamily: 'inherit',
            }}
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            style={{
              padding: '8px 14px', borderRadius: 'var(--grimoire-radius-sm)', fontSize: '13px',
              border: '1px solid rgba(200,123,123,0.25)',
              background: 'rgba(200,123,123,0.12)', color: 'var(--grimoire-error)',
              cursor: 'pointer', transition: 'var(--grimoire-transition)',
              fontFamily: 'inherit',
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
}: SidebarProps) {
  const [hoveredSession, setHoveredSession] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [totalChunks, setTotalChunks] = useState(0)
  const [uniqueSources, setUniqueSources] = useState<string[]>([])
  const { isOnline } = useConnection()
  const { show } = useToast()

  const refreshStats = async () => {
    try {
      const stats = await getCollectionStats()
      setTotalChunks(stats.total_chunks ?? 0)
      setUniqueSources(stats.unique_sources ?? [])
    } catch {
      // Offline — keep last known values, don't blank them out
    }
  }

  useEffect(() => {
    refreshStats()
    const interval = setInterval(refreshStats, 30000)
    return () => clearInterval(interval)
  }, [])

  const handleDeleteClick = (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation()
    if (!isOnline) {
      show("Can't delete while offline — reconnect to continue", 'error')
      return
    }
    onSwitchSession(sessionId)
    setConfirmDelete(true)
  }

  const handleNewConversation = () => {
    // New conversation works offline (frontend-only state)
    onNewSession()
  }

  return (
    <>
      {confirmDelete && (
        <ConfirmDialog
          onConfirm={() => {
            onClearSession()
            setConfirmDelete(false)
          }}
          onCancel={() => setConfirmDelete(false)}
        />
      )}

      <div style={{
        width: '260px', flexShrink: 0,
        display: 'flex', flexDirection: 'column',
        background: 'rgba(12, 14, 16, 0.5)',
        backdropFilter: 'blur(50px) saturate(140%)',
        WebkitBackdropFilter: 'blur(50px) saturate(140%)',
        borderRight: '1px solid var(--grimoire-border)',
        height: '100vh',
      }}>
        {/* Logo block */}
        <div style={{
          padding: '26px 16px 20px',
          borderBottom: '1px solid var(--grimoire-border)',
          display: 'flex', alignItems: 'center', gap: '12px',
        }}>
          <div style={{
            width: '36px', height: '36px',
            borderRadius: '10px',
            background: 'linear-gradient(135deg, #d4c195 0%, #a08967 50%, #8a9d7d 100%)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            flexShrink: 0,
            boxShadow: '0 6px 20px rgba(201, 177, 135, 0.3), inset 0 1px 0 rgba(255,250,235,0.25)',
            position: 'relative', overflow: 'hidden',
          }}>
            <div style={{
              position: 'absolute', inset: 0,
              background: 'radial-gradient(circle at 30% 25%, rgba(255,250,235,0.5), transparent 60%)',
            }} />
            <GrimoireMark
              size={22}
              tint="black"
              style={{ position: 'relative' }}
            />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.2 }}>
            <span style={{
              fontSize: '15px', fontWeight: 500,
              letterSpacing: '-0.3px',
              color: 'var(--grimoire-text-strong)',
            }}>
              Grimoire
            </span>
            <span style={{
              fontSize: '10.5px',
              color: 'var(--grimoire-muted-2)',
              marginTop: '2px',
              letterSpacing: '0.1px',
            }}>
              Knowledge engine
            </span>
          </div>
        </div>

        <UploadPanel
          totalChunks={totalChunks}
          uniqueSources={uniqueSources}
          onIngestComplete={refreshStats}
        />

        <div style={{ padding: '12px 14px 6px' }}>
          <button
            onClick={handleNewConversation}
            style={{
              width: '100%',
              display: 'flex', alignItems: 'center', gap: '10px',
              padding: '10px 13px',
              borderRadius: 'var(--grimoire-radius)',
              border: '1px solid var(--grimoire-border)',
              background: 'var(--grimoire-faint)',
              color: 'var(--grimoire-text-strong)',
              fontSize: '13px', fontWeight: 500,
              cursor: 'pointer',
              transition: 'var(--grimoire-transition)',
              fontFamily: 'inherit',
              letterSpacing: '-0.1px',
              textAlign: 'left',
            }}
            onMouseEnter={e => {
              e.currentTarget.style.borderColor = 'var(--grimoire-border-hover)'
              e.currentTarget.style.background = 'var(--grimoire-faint-2)'
            }}
            onMouseLeave={e => {
              e.currentTarget.style.borderColor = 'var(--grimoire-border)'
              e.currentTarget.style.background = 'var(--grimoire-faint)'
            }}
          >
            <Plus size={14} style={{ color: 'var(--grimoire-muted)' }} strokeWidth={1.8} />
            New conversation
          </button>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: '8px 8px 4px' }}>
          {sessions.length > 0 && (
            <div style={{
              fontSize: '10px',
              color: 'var(--grimoire-muted-2)',
              letterSpacing: '0.8px',
              padding: '0 12px 10px',
              textTransform: 'uppercase',
              fontWeight: 500,
            }}>
              Recent
            </div>
          )}
          {sessions.length === 0 ? (
            <p style={{
              padding: '8px 12px',
              fontSize: '12px',
              color: 'var(--grimoire-muted-2)',
              letterSpacing: '-0.1px',
            }}>
              No conversations yet
            </p>
          ) : (
            sessions.map(session => {
              const active = session.id === currentSessionId
              return (
                <div
                  key={session.id}
                  onMouseEnter={() => setHoveredSession(session.id)}
                  onMouseLeave={() => setHoveredSession(null)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: '10px',
                    padding: '10px 14px',
                    borderRadius: 'var(--grimoire-radius-sm)',
                    background: active
                      ? 'linear-gradient(90deg, rgba(201,177,135,0.1), rgba(201,177,135,0.015))'
                      : 'transparent',
                    borderLeft: active
                      ? '2px solid var(--grimoire-gold)'
                      : '2px solid transparent',
                    marginBottom: '2px',
                    cursor: 'pointer',
                    transition: 'var(--grimoire-transition-fast)',
                  }}
                  onClick={() => onSwitchSession(session.id)}
                  onMouseOver={e => {
                    if (!active) e.currentTarget.style.background = 'var(--grimoire-faint)'
                  }}
                  onMouseOut={e => {
                    if (!active) e.currentTarget.style.background = 'transparent'
                  }}
                >
                  <MessageSquare
                    size={12}
                    strokeWidth={1.8}
                    style={{
                      color: active ? 'var(--grimoire-gold)' : 'var(--grimoire-muted-2)',
                      flexShrink: 0,
                    }}
                  />
                  <span style={{
                    overflow: 'hidden', textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap', flex: 1,
                    fontSize: '12.5px',
                    fontWeight: active ? 500 : 400,
                    letterSpacing: '-0.1px',
                    color: active ? 'var(--grimoire-gold-soft)' : 'var(--grimoire-muted)',
                  }}>
                    {session.label}
                  </span>
                  {hoveredSession === session.id && (
                    <button
                      onClick={e => handleDeleteClick(e, session.id)}
                      title={isOnline ? 'Delete conversation' : "Can't delete — offline"}
                      disabled={!isOnline}
                      style={{
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        width: '20px', height: '20px',
                        borderRadius: '5px',
                        border: 'none', background: 'transparent',
                        color: isOnline
                          ? 'var(--grimoire-muted-2)'
                          : 'rgba(235,231,223,0.18)',
                        cursor: isOnline ? 'pointer' : 'not-allowed',
                        flexShrink: 0,
                        transition: 'var(--grimoire-transition-fast)',
                      }}
                      onMouseEnter={e => {
                        if (isOnline) e.currentTarget.style.color = 'var(--grimoire-error)'
                      }}
                      onMouseLeave={e => {
                        if (isOnline) e.currentTarget.style.color = 'var(--grimoire-muted-2)'
                      }}
                    >
                      <Trash2 size={12} strokeWidth={1.8} />
                    </button>
                  )}
                </div>
              )
            })
          )}
        </div>

        <div style={{
          padding: '14px',
          borderTop: '1px solid var(--grimoire-border)',
          display: 'flex',
          justifyContent: 'flex-start',
          alignItems: 'center',
        }}>
          <HealthIndicator />
        </div>
      </div>
    </>
  )
}