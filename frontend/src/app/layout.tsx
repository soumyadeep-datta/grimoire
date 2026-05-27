import type { Metadata } from 'next'
import './globals.css'
import { ToastProvider } from '@/lib/toast'
import { ConnectionProvider } from '@/lib/connection'

export const metadata: Metadata = {
  title: 'Grimoire — Developer Knowledge Assistant',
  description: 'Agentic RAG system for querying developer documentation',
  icons: {
    icon: '/icons/grimoire-favicon.svg',
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>
        <ConnectionProvider>
          <ToastProvider>
            {children}
          </ToastProvider>
        </ConnectionProvider>
      </body>
    </html>
  )
}