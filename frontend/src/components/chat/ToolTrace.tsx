'use client'
import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ChevronDown, Search, Globe, Database, Code, Loader2, Check } from 'lucide-react'
import { ToolStep } from '@/lib/types'

const TOOL_ICONS: Record<string, React.ReactNode> = {
  rag_retrieval: <Search size={12} strokeWidth={1.8} />,
  web_search: <Globe size={12} strokeWidth={1.8} />,
  database_query: <Database size={12} strokeWidth={1.8} />,
  code_executor: <Code size={12} strokeWidth={1.8} />,
}

const TOOL_LABELS: Record<string, string> = {
  rag_retrieval: 'Documents',
  web_search: 'Web',
  database_query: 'Database',
  code_executor: 'Code',
}

export function ToolTrace({ steps }: { steps: ToolStep[] }) {
  const [open, setOpen] = useState(false)
  if (!steps.length) return null

  const allDone = steps.every(s => s.done)
  const activeStep = steps.find(s => !s.done)

  const summary = allDone
    ? `${steps.length} step${steps.length > 1 ? 's' : ''}`
    : (activeStep?.status.toLowerCase() ?? 'thinking')

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
        {!allDone ? (
          <Loader2 size={11} className="animate-spin" style={{ color: 'var(--grimoire-gold)' }} />
        ) : (
          <span
            style={{
              width: '5px', height: '5px', borderRadius: '50%',
              background: 'var(--grimoire-gold)',
              animation: 'grimoire-breathe 6s ease-in-out infinite',
            }}
          />
        )}
        <span>{summary}</span>
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
              padding: '14px 16px',
              borderRadius: 'var(--grimoire-radius)',
              border: '1px solid var(--grimoire-border)',
              background: 'var(--grimoire-faint)',
            }}>
              <div style={{ position: 'relative' }}>
                {steps.map((step, i) => {
                  const isLast = i === steps.length - 1
                  const icon = TOOL_ICONS[step.tool] ?? <Search size={12} strokeWidth={1.8} />
                  const label = TOOL_LABELS[step.tool] ?? step.tool

                  // When done: show the original search query (dimmed) + result
                  // When active: show current status (the search query)
                  const showQuery = step.done && step.searchQuery && step.searchQuery !== step.status
                  const displayStatus = step.status

                  return (
                    <div
                      key={step.id}
                      style={{
                        display: 'flex',
                        gap: '12px',
                        paddingBottom: isLast ? 0 : '16px',
                        position: 'relative',
                      }}
                    >
                      {/* Connecting line */}
                      {!isLast && (
                        <div style={{
                          position: 'absolute',
                          left: '11px',
                          top: '24px',
                          bottom: '0',
                          width: '1.5px',
                          background: 'linear-gradient(to bottom, rgba(201,177,135,0.3), rgba(201,177,135,0.1))',
                        }} />
                      )}

                      {/* Node marker */}
                      <div style={{
                        width: '24px', height: '24px',
                        borderRadius: '7px',
                        flexShrink: 0,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        background: step.done
                          ? 'rgba(132, 169, 140, 0.12)'
                          : 'rgba(201, 177, 135, 0.12)',
                        color: step.done
                          ? 'var(--grimoire-success)'
                          : 'var(--grimoire-gold)',
                        position: 'relative',
                        zIndex: 1,
                      }}>
                        {step.done
                          ? <Check size={12} strokeWidth={2.2} />
                          : icon}
                      </div>

                      {/* Step text */}
                      <div style={{ flex: 1, minWidth: 0, paddingTop: '1px' }}>
                        <div style={{
                          fontSize: '12px',
                          fontWeight: 500,
                          color: 'var(--grimoire-text-strong)',
                          letterSpacing: '-0.1px',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '7px',
                        }}>
                          {label}
                          {!step.done && (
                            <Loader2 size={10} className="animate-spin" style={{ color: 'var(--grimoire-muted-2)' }} />
                          )}
                        </div>

                        {/* Show original search query when step is done */}
                        {showQuery && (
                          <div style={{
                            fontSize: '11px',
                            color: 'var(--grimoire-muted-2)',
                            letterSpacing: '-0.1px',
                            marginTop: '2px',
                            lineHeight: '1.4',
                            fontStyle: 'italic',
                          }}>
                            {step.searchQuery}
                          </div>
                        )}

                        {/* Current status / result */}
                        <div style={{
                          fontSize: '11.5px',
                          color: step.done
                            ? 'var(--grimoire-success)'
                            : 'var(--grimoire-muted)',
                          letterSpacing: '-0.1px',
                          marginTop: showQuery ? '1px' : '2px',
                          lineHeight: '1.5',
                        }}>
                          {displayStatus}
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}