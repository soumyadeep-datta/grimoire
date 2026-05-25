'use client'
import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { WifiOff, RefreshCw } from 'lucide-react'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export function ConnectionBanner() {
  const [isOffline, setIsOffline] = useState(false)
  const [retrying, setRetrying] = useState(false)

  const checkHealth = async () => {
    try {
      const res = await fetch(`${API_BASE}/health`, {
        signal: AbortSignal.timeout(3000),
      })
      setIsOffline(!res.ok)
    } catch {
      setIsOffline(true)
    }
  }

  const handleRetry = async () => {
    setRetrying(true)
    await checkHealth()
    setRetrying(false)
  }

  useEffect(() => {
    checkHealth()
    // Faster polling when offline (5s), slower when online (30s)
    const interval = setInterval(checkHealth, isOffline ? 5000 : 30000)
    return () => clearInterval(interval)
  }, [isOffline])

  return (
    <AnimatePresence>
      {isOffline && (
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -20 }}
          transition={{ duration: 0.2 }}
          style={{
            position: 'absolute',
            top: '12px',
            left: '50%',
            transform: 'translateX(-50%)',
            zIndex: 50,
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            padding: '8px 14px',
            borderRadius: '999px',
            background: 'rgba(239,68,68,0.12)',
            border: '1px solid rgba(239,68,68,0.3)',
            backdropFilter: 'blur(12px)',
            color: '#fca5a5',
            fontSize: '12px',
            fontWeight: 500,
            boxShadow: '0 4px 20px rgba(239,68,68,0.15)',
          }}
        >
          <WifiOff size={13} style={{ flexShrink: 0 }} />
          <span>Can't reach the server</span>
          <button
            onClick={handleRetry}
            disabled={retrying}
            style={{
              display: 'flex', alignItems: 'center', gap: '4px',
              padding: '3px 10px', borderRadius: '999px',
              border: '1px solid rgba(239,68,68,0.3)',
              background: 'rgba(239,68,68,0.08)',
              color: '#fca5a5',
              fontSize: '11px', fontWeight: 500,
              cursor: retrying ? 'not-allowed' : 'pointer',
              transition: 'all 0.15s',
            }}
            onMouseEnter={e => {
              if (!retrying) e.currentTarget.style.background = 'rgba(239,68,68,0.15)'
            }}
            onMouseLeave={e => {
              if (!retrying) e.currentTarget.style.background = 'rgba(239,68,68,0.08)'
            }}
          >
            <RefreshCw size={10} className={retrying ? 'animate-spin' : ''} />
            {retrying ? 'Checking...' : 'Retry'}
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  )
}