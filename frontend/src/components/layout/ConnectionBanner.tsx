'use client'
import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { WifiOff, RefreshCw } from 'lucide-react'
import { useConnection } from '@/lib/connection'

export function ConnectionBanner() {
  const { isOnline, recheck } = useConnection()
  const [retrying, setRetrying] = useState(false)

  const handleRetry = async () => {
    setRetrying(true)
    await recheck()
    setRetrying(false)
  }

  return (
    <AnimatePresence>
      {!isOnline && (
        <motion.div
          initial={{ opacity: 0, y: -16 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -16 }}
          transition={{ duration: 0.38, ease: [0.4, 0, 0.2, 1] }}
          style={{
            position: 'absolute',
            top: '16px',
            left: '50%',
            transform: 'translateX(-50%)',
            zIndex: 50,
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            padding: '9px 16px',
            borderRadius: '999px',
            background: 'rgba(200, 123, 123, 0.1)',
            border: '1px solid rgba(200, 123, 123, 0.25)',
            backdropFilter: 'blur(24px) saturate(140%)',
            WebkitBackdropFilter: 'blur(24px) saturate(140%)',
            color: 'var(--grimoire-error)',
            fontSize: '12px',
            fontWeight: 500,
            letterSpacing: '-0.1px',
            boxShadow: '0 8px 32px rgba(200, 123, 123, 0.15), inset 0 1px 0 rgba(255,250,235,0.05)',
          }}
        >
          <WifiOff size={13} strokeWidth={1.8} style={{ flexShrink: 0 }} />
          <span>Can&apos;t reach the server</span>
          <button
            onClick={handleRetry}
            disabled={retrying}
            style={{
              display: 'flex', alignItems: 'center', gap: '5px',
              padding: '4px 11px',
              borderRadius: '999px',
              border: '1px solid rgba(200, 123, 123, 0.3)',
              background: 'rgba(200, 123, 123, 0.08)',
              color: 'var(--grimoire-error)',
              fontSize: '11px', fontWeight: 500,
              cursor: retrying ? 'not-allowed' : 'pointer',
              transition: 'var(--grimoire-transition-fast)',
              fontFamily: 'inherit',
              letterSpacing: '-0.1px',
            }}
            onMouseEnter={e => {
              if (!retrying) e.currentTarget.style.background = 'rgba(200, 123, 123, 0.15)'
            }}
            onMouseLeave={e => {
              if (!retrying) e.currentTarget.style.background = 'rgba(200, 123, 123, 0.08)'
            }}
          >
            <RefreshCw size={10} strokeWidth={2} className={retrying ? 'animate-spin' : ''} />
            {retrying ? 'Checking...' : 'Retry'}
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  )
}