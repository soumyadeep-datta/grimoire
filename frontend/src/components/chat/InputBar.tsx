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
  const [isFocused, setIsFocused] = useState(false)
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

  const isDisabled = !value.trim() || isStreaming

  return (
    <div style={{
      padding: '20px 56px 28px',
      background: 'transparent',
    }}>
      <div style={{
        display: 'flex',
        alignItems: 'flex-end',
        gap: '12px',
        padding: '13px 16px',
        borderRadius: 'var(--grimoire-radius-lg)',
        border: `1px solid ${isFocused
          ? 'rgba(201, 177, 135, 0.25)'
          : 'var(--grimoire-border-hover)'}`,
        background: 'rgba(26, 20, 16, 0.6)',
        backdropFilter: 'blur(28px) saturate(140%)',
        WebkitBackdropFilter: 'blur(28px) saturate(140%)',
        transition: 'var(--grimoire-transition)',
        boxShadow: isFocused
          ? '0 12px 40px rgba(0,0,0,0.4), 0 0 0 3px rgba(201, 177, 135, 0.08), inset 0 1px 0 rgba(255,250,235,0.04)'
          : '0 12px 40px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,250,235,0.04)',
      }}>
        <textarea
          ref={textareaRef}
          value={value}
          onChange={e => setValue(e.target.value)}
          onKeyDown={handleKey}
          onInput={handleInput}
          onFocus={() => setIsFocused(true)}
          onBlur={() => setIsFocused(false)}
          placeholder="Ask about your documents..."
          disabled={isStreaming}
          rows={1}
          style={{
            flex: 1,
            background: 'transparent',
            border: 'none',
            outline: 'none',
            resize: 'none',
            color: 'var(--grimoire-text-strong)',
            fontSize: '14.5px',
            lineHeight: '1.6',
            fontFamily: 'inherit',
            letterSpacing: '-0.1px',
            maxHeight: '160px',
            overflowY: 'auto',
            opacity: isStreaming ? 0.5 : 1,
            paddingTop: '5px',
            paddingBottom: '5px',
          }}
        />
        <motion.button
          whileTap={!isDisabled ? { scale: 0.92 } : undefined}
          onClick={handleSend}
          disabled={isDisabled}
          style={{
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            width: '34px', height: '34px',
            borderRadius: 'var(--grimoire-radius)',
            border: 'none',
            cursor: isDisabled ? 'not-allowed' : 'pointer',
            background: isDisabled
              ? 'rgba(201, 177, 135, 0.1)'
              : 'linear-gradient(135deg, var(--grimoire-gold), var(--grimoire-sage))',
            color: isDisabled
              ? 'rgba(201, 177, 135, 0.4)'
              : '#2b2618',
            flexShrink: 0,
            transition: 'var(--grimoire-transition)',
            boxShadow: isDisabled
              ? 'none'
              : '0 4px 16px rgba(201, 177, 135, 0.25)',
          }}
        >
          {isStreaming
            ? <Loader2 size={15} className="animate-spin" />
            : <Send size={14} strokeWidth={2.2} />
          }
        </motion.button>
      </div>
      <div style={{
        marginTop: '10px',
        textAlign: 'center',
        fontSize: '10.5px',
        color: 'var(--grimoire-faint-text)',
        letterSpacing: '0.1px',
      }}>
        Shift + Enter for new line
      </div>
    </div>
  )
}