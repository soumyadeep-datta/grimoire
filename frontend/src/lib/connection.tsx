'use client'
import { createContext, useContext, useEffect, useState, ReactNode } from 'react'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface ConnectionContextValue {
  isOnline: boolean
  recheck: () => Promise<void>
}

const ConnectionContext = createContext<ConnectionContextValue>({
  isOnline: true,
  recheck: async () => {},
})

/**
 * Single source of truth for backend connectivity status.
 * One health-check loop drives everything (banner, indicator, disabled buttons).
 */
export function ConnectionProvider({ children }: { children: ReactNode }) {
  const [isOnline, setIsOnline] = useState(true)

  const recheck = async () => {
    try {
      const res = await fetch(`${API_BASE}/health`, {
        signal: AbortSignal.timeout(3000),
      })
      setIsOnline(res.ok)
    } catch {
      setIsOnline(false)
    }
  }

  useEffect(() => {
    recheck()
    // Poll faster when offline to recover quickly, slower when online
    const interval = setInterval(recheck, isOnline ? 30000 : 5000)
    return () => clearInterval(interval)
  }, [isOnline])

  return (
    <ConnectionContext.Provider value={{ isOnline, recheck }}>
      {children}
    </ConnectionContext.Provider>
  )
}

export const useConnection = () => useContext(ConnectionContext)