'use client'
import { motion } from 'framer-motion'
import { useConnection } from '@/lib/connection'

export function HealthIndicator() {
  const { isOnline } = useConnection()

  const config = isOnline
    ? {
        color: 'var(--grimoire-gold)',
        glow: 'rgba(201, 177, 135, 0.35)',
        label: 'Connected',
        labelColor: 'var(--grimoire-muted)',
      }
    : {
        color: 'var(--grimoire-error)',
        glow: 'rgba(200, 123, 123, 0.3)',
        label: 'Offline',
        labelColor: 'var(--grimoire-error)',
      }

  return (
    <div
      title={config.label}
      style={{
        display: 'flex', alignItems: 'center', gap: '8px',
        padding: '4px 8px',
        fontSize: '11px',
        letterSpacing: '-0.1px',
      }}
    >
      <motion.div
        style={{
          width: '6px',
          height: '6px',
          borderRadius: '50%',
          background: config.color,
          boxShadow: isOnline ? `0 0 10px ${config.glow}` : 'none',
          flexShrink: 0,
          animation: isOnline
            ? 'grimoire-pulse-slow 4s ease-in-out infinite'
            : 'none',
        }}
      />
      <span style={{
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
        color: config.labelColor,
      }}>
        {config.label}
      </span>
    </div>
  )
}