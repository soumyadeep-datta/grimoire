'use client'
import { useState, useRef, KeyboardEvent } from 'react'
import { Send, Loader2 } from 'lucide-react'
import { motion } from 'framer-motion'

interface InputBarProps {
  onSend: (message: string) => void
  isStreaming: boolean
}

export function InputBar({ onSend, isStreaming }: InputBarProps) {
  const [value, setValue] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const handleSend = () => {
    const trimmed = value.trim()
    if (!trimmed || isStreaming) return
    onSend(trimmed)
    setValue('')
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
  }

  const handleKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleInput = () => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 160) + 'px'
  }

  return (
    <div style={{
      padding: '16px 20px 20px',
      borderTop: '1px solid var(--grimoire-border)',
      background: 'var(--grimoire-deep)',
    }}>
      <div style={{
        display: 'flex',
        alignItems: 'flex-end',
        gap: '10px',
        padding: '10px 14px',
        borderRadius: '14px',
        border: '1px solid var(--grimoire-border)',
        background: 'var(--grimoire-surface)',
        transition: 'border-color 0.2s',
      }}
        onFocus={e => (e.currentTarget.style.borderColor = 'var(--grimoire-border-hover)')}
        onBlur={e => (e.currentTarget.style.borderColor = 'var(--grimoire-border)')}
      >
        <textarea
          ref={textareaRef}
          value={value}
          onChange={e => setValue(e.target.value)}
          onKeyDown={handleKey}
          onInput={handleInput}
          placeholder="Ask about your documentation..."
          disabled={isStreaming}
          rows={1}
          style={{
            flex: 1, background: 'transparent', border: 'none', outline: 'none',
            resize: 'none', color: 'var(--grimoire-text)', fontSize: '14px',
            lineHeight: '1.6', fontFamily: 'inherit',
            maxHeight: '160px', overflowY: 'auto',
            opacity: isStreaming ? 0.5 : 1,
          }}
        />
        <motion.button
          whileTap={{ scale: 0.9 }}
          onClick={handleSend}
          disabled={!value.trim() || isStreaming}
          style={{
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            width: '34px', height: '34px', borderRadius: '10px',
            border: 'none', cursor: !value.trim() || isStreaming ? 'not-allowed' : 'pointer',
            background: !value.trim() || isStreaming
              ? 'rgba(139,92,246,0.15)'
              : 'linear-gradient(135deg, #8b5cf6, #6d28d9)',
            color: '#fff', flexShrink: 0, transition: 'all 0.2s',
          }}
        >
          {isStreaming
            ? <Loader2 size={15} className="animate-spin" />
            : <Send size={15} />
          }
        </motion.button>
      </div>
      <p style={{ marginTop: '8px', textAlign: 'center', fontSize: '11px', color: 'var(--grimoire-muted)' }}>
        Shift+Enter for new line · Enter to send
      </p>
    </div>
  )
}