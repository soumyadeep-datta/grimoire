'use client'
import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

type HealthStatus = 'connected' | 'disconnected' | 'checking'

export function HealthIndicator() {
  const [status, setStatus] = useState<HealthStatus>('checking')

  const checkHealth = async () => {
    try {
      const res = await fetch(`${API_BASE}/health`, {
        signal: AbortSignal.timeout(3000),
      })
      setStatus(res.ok ? 'connected' : 'disconnected')
    } catch {
      setStatus('disconnected')
    }
  }

  useEffect(() => {
    checkHealth()
    // Poll every 15 seconds
    const interval = setInterval(checkHealth, 15000)
    return () => clearInterval(interval)
  }, [])

  const config = {
    connected: { color: '#10b981', label: 'Connected', pulse: false },
    disconnected: { color: '#ef4444', label: 'Backend offline', pulse: false },
    checking: { color: '#64748b', label: 'Checking...', pulse: true },
  }[status]

  return (
    <div
      title={config.label}
      style={{
        display: 'flex', alignItems: 'center', gap: '6px',
        padding: '4px 8px', fontSize: '11px',
        color: 'var(--grimoire-muted)',
      }}
    >
      <motion.div
        animate={config.pulse ? { opacity: [0.4, 1, 0.4] } : {}}
        transition={{ duration: 1.5, repeat: Infinity, ease: 'easeInOut' }}
        style={{
          width: '7px', height: '7px', borderRadius: '50%',
          background: config.color,
          boxShadow: status === 'connected' ? `0 0 8px ${config.color}55` : 'none',
          flexShrink: 0,
        }}
      />
      <span style={{
        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        color: status === 'disconnected' ? '#fca5a5' : 'var(--grimoire-muted)',
      }}>
        {config.label}
      </span>
    </div>
  )
}