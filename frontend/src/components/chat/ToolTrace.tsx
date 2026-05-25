'use client'
import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ChevronDown, Search, Globe, Database, Code, Loader2, CheckCircle2 } from 'lucide-react'
import { ToolStatus } from '@/lib/types'

const TOOL_ICONS: Record<string, React.ReactNode> = {
  rag_retrieval: <Search size={13} />,
  web_search: <Globe size={13} />,
  database_query: <Database size={13} />,
  code_executor: <Code size={13} />,
}

const TOOL_LABELS: Record<string, string> = {
  rag_retrieval: 'Docs',
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
    <div className="mb-3">
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          padding: '5px 10px',
          borderRadius: '20px',
          border: '1px solid var(--grimoire-border)',
          background: 'transparent',
          color: 'var(--grimoire-muted)',
          fontSize: '12px',
          cursor: 'pointer',
          transition: 'all 0.2s',
        }}
        onMouseEnter={e => {
          const el = e.currentTarget
          el.style.borderColor = 'var(--grimoire-border-hover)'
          el.style.color = 'var(--grimoire-violet-bright)'
        }}
        onMouseLeave={e => {
          const el = e.currentTarget
          el.style.borderColor = 'var(--grimoire-border)'
          el.style.color = 'var(--grimoire-muted)'
        }}
      >
        {!allDone && activeTools.length > 0 ? (
          <Loader2 size={12} className="animate-spin" style={{ color: 'var(--grimoire-violet)' }} />
        ) : (
          <CheckCircle2 size={12} style={{ color: 'var(--grimoire-violet)' }} />
        )}
        <span>
          {!allDone && activeTools.length > 0
            ? activeTools[0].status
            : `${tools.length} tool${tools.length > 1 ? 's' : ''} used`}
        </span>
        <motion.div animate={{ rotate: open ? 180 : 0 }} transition={{ duration: 0.2 }}>
          <ChevronDown size={12} />
        </motion.div>
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2 }}
            style={{ overflow: 'hidden' }}
          >
            <div style={{
              marginTop: '8px',
              padding: '10px 12px',
              borderRadius: '10px',
              border: '1px solid var(--grimoire-border)',
              background: 'var(--grimoire-faint)',
              display: 'flex',
              flexDirection: 'column',
              gap: '8px',
            }}>
              {tools.map((tool, i) => (
                <div key={i} style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  fontSize: '12px',
                }}>
                  <span style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    width: '22px',
                    height: '22px',
                    borderRadius: '6px',
                    background: 'rgba(139, 92, 246, 0.12)',
                    color: 'var(--grimoire-violet)',
                    flexShrink: 0,
                  }}>
                    {TOOL_ICONS[tool.tool] ?? <Search size={13} />}
                  </span>
                  <span style={{ color: 'var(--grimoire-text)', fontWeight: 500 }}>
                    {TOOL_LABELS[tool.tool] ?? tool.tool}
                  </span>
                  <span style={{ color: 'var(--grimoire-muted)', flex: 1 }}>
                    {tool.status}
                  </span>
                  {tool.done
                    ? <CheckCircle2 size={12} style={{ color: 'var(--grimoire-violet)', flexShrink: 0 }} />
                    : <Loader2 size={12} className="animate-spin" style={{ color: 'var(--grimoire-muted)', flexShrink: 0 }} />
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