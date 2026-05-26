'use client'
import { useState } from 'react'
import { Sidebar } from '@/components/layout/Sidebar'
import { ChatWindow } from '@/components/chat/ChatWindow'
import { InputBar } from '@/components/chat/InputBar'
import { ConnectionBanner } from '@/components/layout/ConnectionBanner'
import { useChat } from '@/hooks/useChat'

export default function Home() {
  const [isDark, setIsDark] = useState(true)
  const {
    messages, sessions, currentSessionId, isStreaming,
    sendMessage, retryMessage, newSession, switchSession, clearSession,
  } = useChat()

  return (
    <div className={isDark ? '' : 'light'} style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      {/* Animated background */}
      <div style={{
        position: 'fixed', inset: 0, pointerEvents: 'none', zIndex: 0,
        background: isDark
          ? 'radial-gradient(ellipse at 20% 50%, rgba(139,92,246,0.06) 0%, transparent 60%), radial-gradient(ellipse at 80% 20%, rgba(236,72,153,0.04) 0%, transparent 50%)'
          : 'radial-gradient(ellipse at 20% 50%, rgba(109,40,217,0.04) 0%, transparent 60%)',
      }} />

      <div style={{ position: 'relative', zIndex: 1, display: 'flex', width: '100%', height: '100vh' }}>
        <Sidebar
          sessions={sessions}
          currentSessionId={currentSessionId}
          onNewSession={newSession}
          onSwitchSession={switchSession}
          onClearSession={clearSession}
          onToggleTheme={() => setIsDark(d => !d)}
        />

        {/* Main chat area */}
        <div style={{
          flex: 1, display: 'flex', flexDirection: 'column',
          background: 'var(--grimoire-void)', overflow: 'hidden',
          position: 'relative',
        }}>
          <ConnectionBanner />
          <ChatWindow
            messages={messages}
            isDark={isDark}
            onSendSuggestion={sendMessage}
            onRetry={retryMessage}
          />
          <InputBar onSend={sendMessage} isStreaming={isStreaming} />
        </div>
      </div>

      <style>{`
        @keyframes blink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0; }
        }
      `}</style>
    </div>
  )
}