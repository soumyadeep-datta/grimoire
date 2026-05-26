'use client'
import { createContext, useContext, useState, ReactNode, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { AlertCircle, CheckCircle2, Info } from 'lucide-react'

type ToastKind = 'info' | 'success' | 'error'

interface Toast {
  id: string
  kind: ToastKind
  message: string
}

interface ToastContextValue {
  show: (message: string, kind?: ToastKind) => void
}

const ToastContext = createContext<ToastContextValue>({
  show: () => {},
})

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const show = useCallback((message: string, kind: ToastKind = 'info') => {
    const id = Math.random().toString(36).slice(2)
    setToasts(prev => [...prev, { id, kind, message }])
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id))
    }, 4000)
  }, [])

  return (
    <ToastContext.Provider value={{ show }}>
      {children}
      <div style={{
        position: 'fixed',
        bottom: '24px',
        right: '24px',
        zIndex: 1000,
        display: 'flex',
        flexDirection: 'column',
        gap: '8px',
        pointerEvents: 'none',
      }}>
        <AnimatePresence>
          {toasts.map(toast => {
            const config = {
              info: {
                bg: 'rgba(201, 177, 135, 0.1)',
                border: 'rgba(201, 177, 135, 0.25)',
                color: 'var(--grimoire-gold-bright)',
                Icon: Info,
              },
              success: {
                bg: 'rgba(132, 169, 140, 0.1)',
                border: 'rgba(132, 169, 140, 0.25)',
                color: 'var(--grimoire-success)',
                Icon: CheckCircle2,
              },
              error: {
                bg: 'rgba(200, 123, 123, 0.1)',
                border: 'rgba(200, 123, 123, 0.25)',
                color: 'var(--grimoire-error)',
                Icon: AlertCircle,
              },
            }[toast.kind]
            const { Icon } = config

            return (
              <motion.div
                key={toast.id}
                initial={{ opacity: 0, x: 16 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 16 }}
                transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '10px',
                  padding: '10px 14px',
                  borderRadius: 'var(--grimoire-radius)',
                  background: config.bg,
                  border: `1px solid ${config.border}`,
                  backdropFilter: 'blur(24px) saturate(140%)',
                  WebkitBackdropFilter: 'blur(24px) saturate(140%)',
                  color: config.color,
                  fontSize: '12.5px',
                  fontWeight: 500,
                  letterSpacing: '-0.1px',
                  maxWidth: '320px',
                  boxShadow: '0 8px 32px rgba(0,0,0,0.3)',
                  pointerEvents: 'auto',
                }}
              >
                <Icon size={14} strokeWidth={1.8} style={{ flexShrink: 0 }} />
                <span style={{ flex: 1 }}>{toast.message}</span>
              </motion.div>
            )
          })}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  )
}

export const useToast = () => useContext(ToastContext)