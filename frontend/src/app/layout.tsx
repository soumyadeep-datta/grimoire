import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Grimoire — Developer Knowledge Assistant',
  description: 'Agentic RAG system for querying developer documentation',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}