'use client'
import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ChevronDown, Search, Globe, Database, Code, Loader2, CheckCircle2 } from 'lucide-react'
import { ToolStatus } from '@/lib/types'

const TOOL_ICONS: Record<string, React.ReactNode> = {
  rag_retrieval: <Search size={13} strokeWidth={1.8} />,
  web_search: <Globe size={13} strokeWidth={1.8} />,
  database_query: <Database size={13} strokeWidth={1.8} />,
  code_executor: <Code size={13} strokeWidth={1.8} />,
}

const TOOL_LABELS: Record<string, string> = {
  rag_retrieval: 'Documents',
  web_search: 'Web',
  database_query: 'Database',
  code_executor: 'Code',
}

export function ToolTrace({ tools }: { tools: ToolStatus[] }) {
  const [open, setOpen] = useState(false)
  if (!tools.length) return null

  const allDone = tools.every(t => t.done)
  const activeTools = tools.filter(t => !t.done)

  return (
    <div style={{ marginBottom: '14px' }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '7px',
          padding: '5px 12px',
          borderRadius: '999px',
          border: '1px solid rgba(201, 177, 135, 0.16)',
          background: 'rgba(201, 177, 135, 0.04)',
          color: 'var(--grimoire-gold-bright)',
          fontSize: '11.5px',
          fontWeight: 500,
          cursor: 'pointer',
          transition: 'var(--grimoire-transition-fast)',
          letterSpacing: '-0.1px',
          fontFamily: 'inherit',
        }}
        onMouseEnter={e => {
          const el = e.currentTarget
          el.style.borderColor = 'rgba(201, 177, 135, 0.3)'
          el.style.background = 'rgba(201, 177, 135, 0.08)'
        }}
        onMouseLeave={e => {
          const el = e.currentTarget
          el.style.borderColor = 'rgba(201, 177, 135, 0.16)'
          el.style.background = 'rgba(201, 177, 135, 0.04)'
        }}
      >
        {!allDone && activeTools.length > 0 ? (
          <Loader2
            size={11}
            className="animate-spin"
            style={{ color: 'var(--grimoire-gold)' }}
          />
        ) : (
          <span
            className="breathe-static"
            style={{
              width: '5px',
              height: '5px',
              borderRadius: '50%',
              background: 'var(--grimoire-gold)',
              animation: 'grimoire-breathe 6s ease-in-out infinite',
            }}
          />
        )}
        <span>
          {!allDone && activeTools.length > 0
            ? activeTools[0].status.toLowerCase()
            : `${tools.length} tool${tools.length > 1 ? 's' : ''} used`}
        </span>
        <motion.div
          animate={{ rotate: open ? 180 : 0 }}
          transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
        >
          <ChevronDown size={11} strokeWidth={1.8} />
        </motion.div>
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
            style={{ overflow: 'hidden' }}
          >
            <div style={{
              marginTop: '10px',
              padding: '12px 14px',
              borderRadius: 'var(--grimoire-radius)',
              border: '1px solid var(--grimoire-border)',
              background: 'var(--grimoire-faint)',
              display: 'flex',
              flexDirection: 'column',
              gap: '10px',
            }}>
              {tools.map((tool, i) => (
                <div key={i} style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '10px',
                  fontSize: '12px',
                }}>
                  <span style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    width: '24px',
                    height: '24px',
                    borderRadius: '7px',
                    background: 'rgba(201, 177, 135, 0.1)',
                    color: 'var(--grimoire-gold)',
                    flexShrink: 0,
                  }}>
                    {TOOL_ICONS[tool.tool] ?? <Search size={13} strokeWidth={1.8} />}
                  </span>
                  <span style={{
                    color: 'var(--grimoire-text-strong)',
                    fontWeight: 500,
                    letterSpacing: '-0.1px',
                  }}>
                    {TOOL_LABELS[tool.tool] ?? tool.tool}
                  </span>
                  <span style={{
                    color: 'var(--grimoire-muted)',
                    flex: 1,
                    letterSpacing: '-0.1px',
                  }}>
                    {tool.status}
                  </span>
                  {tool.done
                    ? <CheckCircle2
                        size={12}
                        strokeWidth={1.8}
                        style={{ color: 'var(--grimoire-success)', flexShrink: 0 }}
                      />
                    : <Loader2
                        size={12}
                        className="animate-spin"
                        style={{ color: 'var(--grimoire-muted)', flexShrink: 0 }}
                      />
                  }
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}