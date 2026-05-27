'use client'
import { Sidebar } from '@/components/layout/Sidebar'
import { ChatWindow } from '@/components/chat/ChatWindow'
import { InputBar } from '@/components/chat/InputBar'
import { ConnectionBanner } from '@/components/layout/ConnectionBanner'
import { AuroraBackground } from '@/components/layout/AuroraBackground'
import { useChat } from '@/hooks/useChat'

export default function Home() {
  const {
    messages, sessions, currentSessionId, isStreaming,
    sendMessage, retryMessage, newSession, switchSession, clearSession,
  } = useChat()

  return (
    <div
      style={{
        display: 'flex',
        height: '100vh',
        overflow: 'hidden',
        background: 'var(--grimoire-void)',
        position: 'relative',
      }}
    >
      <AuroraBackground />

      <div style={{
        position: 'relative',
        zIndex: 1,
        display: 'flex',
        width: '100%',
        height: '100vh',
      }}>
        <Sidebar
          sessions={sessions}
          currentSessionId={currentSessionId}
          onNewSession={newSession}
          onSwitchSession={switchSession}
          onClearSession={clearSession}
        />

        <div style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          background: 'transparent',
          overflow: 'hidden',
          position: 'relative',
        }}>
          <ConnectionBanner />
          <ChatWindow
            messages={messages}
            onSendSuggestion={sendMessage}
            onRetry={retryMessage}
          />
          <InputBar onSend={sendMessage} isStreaming={isStreaming} />
        </div>
      </div>
    </div>
  )
}
