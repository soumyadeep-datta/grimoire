'use client'
import { createContext, useContext, useEffect, useState, ReactNode, useCallback } from 'react'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface ConnectionContextValue {
  isOnline: boolean
  recheck: () => Promise<void>
  /** Call this from API error handlers to trigger an immediate health check. */
  markPossiblyOffline: () => void
}

const ConnectionContext = createContext<ConnectionContextValue>({
  isOnline: true,
  recheck: async () => {},
  markPossiblyOffline: () => {},
})

/**
 * Single source of truth for backend connectivity status.
 * One health-check loop drives everything (banner, indicator, disabled buttons).
 *
 * Components can also call markPossiblyOffline() from their error handlers
 * to trigger an immediate health check instead of waiting for the next poll.
 * This keeps the offline banner and disabled-button states in sync with
 * what the user is actually seeing.
 */
export function ConnectionProvider({ children }: { children: ReactNode }) {
  const [isOnline, setIsOnline] = useState(true)

  const recheck = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/health`, {
        signal: AbortSignal.timeout(3000),
      })
      setIsOnline(res.ok)
    } catch {
      setIsOnline(false)
    }
  }, [])

  const markPossiblyOffline = useCallback(() => {
    // Don't blindly set offline — verify with a fresh health check first.
    // The original API call might have failed for unrelated reasons (404, 500,
    // rate limit) while the backend is still alive.
    recheck()
  }, [recheck])

  useEffect(() => {
    recheck()
    const interval = setInterval(recheck, isOnline ? 30000 : 5000)
    return () => clearInterval(interval)
  }, [isOnline, recheck])

  return (
    <ConnectionContext.Provider value={{ isOnline, recheck, markPossiblyOffline }}>
      {children}
    </ConnectionContext.Provider>
  )
}

export const useConnection = () => useContext(ConnectionContext)