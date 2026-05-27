'use client'
import { useState, useRef, DragEvent, ChangeEvent } from 'react'
import { Upload, FileText, CheckCircle2, AlertCircle, Loader2, X, ChevronDown } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { deleteSource } from '@/lib/api'
import { useConnection } from '@/lib/connection'
import { useToast } from '@/lib/toast'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface UploadPanelProps {
  totalChunks: number
  uniqueSources?: string[]
  onIngestComplete: () => void
  onIngestingChange?: (ingesting: boolean) => void
}

type UploadStatus =
  | { state: 'idle' }
  | { state: 'uploading'; fileName: string }
  | { state: 'success'; fileName: string; chunks: number }
  | { state: 'error'; message: string }

export function UploadPanel({
  totalChunks,
  uniqueSources = [],
  onIngestComplete,
  onIngestingChange,
}: UploadPanelProps) {
  const [isDragging, setIsDragging] = useState(false)
  const [status, setStatus] = useState<UploadStatus>({ state: 'idle' })
  const [expanded, setExpanded] = useState(false)
  const [deleting, setDeleting] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const { isOnline, markPossiblyOffline } = useConnection()
  const { show } = useToast()

  const handleDelete = async (source: string, e: React.MouseEvent) => {
    e.stopPropagation()
    if (deleting) return
    if (!isOnline) {
      show("Can't delete while offline — reconnect to continue", 'error')
      return
    }
    setDeleting(source)
    try {
      await deleteSource(source)
      onIngestComplete()
    } catch (err) {
      // Network-style failure means backend is probably down — recheck health
      // so the UI updates immediately instead of waiting for the next poll.
      const isNetworkError = err instanceof TypeError ||
        (err instanceof Error && err.message.toLowerCase().includes('fetch'))
      if (isNetworkError) {
        markPossiblyOffline()
        show("Lost connection to server — try again when reconnected", 'error')
      } else {
        show('Delete failed — please try again', 'error')
      }
    } finally {
      setDeleting(null)
    }
  }

  const handleFiles = async (files: FileList | null) => {
    if (!files || files.length === 0) return

    if (!isOnline) {
      show("Can't upload while offline — reconnect to continue", 'error')
      return
    }

    const file = files[0]
    setStatus({ state: 'uploading', fileName: file.name })
    onIngestingChange?.(true)

    const formData = new FormData()
    formData.append('file', file)

    try {
      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), 5 * 60 * 1000)

      const res = await fetch(`${API_BASE}/ingest`, {
        method: 'POST',
        body: formData,
        signal: controller.signal,
      })

      clearTimeout(timeoutId)

      if (!res.ok) {
        const error = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }))
        throw new Error(error.detail ?? 'Upload failed')
      }

      const data = await res.json()
      setStatus({
        state: 'success',
        fileName: file.name,
        chunks: data.chunks_added ?? 0,
      })
      onIngestComplete()
      setTimeout(() => setStatus({ state: 'idle' }), 3000)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Upload failed'
      setStatus({ state: 'error', message: msg })
      setTimeout(() => setStatus({ state: 'idle' }), 5000)
    } finally {
      onIngestingChange?.(false)
    }
  }

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragging(false)
    handleFiles(e.dataTransfer.files)
  }

  const onDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragging(true)
  }

  const onDragLeave = () => setIsDragging(false)

  const onChange = (e: ChangeEvent<HTMLInputElement>) => {
    handleFiles(e.target.files)
    if (inputRef.current) inputRef.current.value = ''
  }

  const isUploading = status.state === 'uploading'

  return (
    <div style={{
      padding: '16px 14px 0',
      display: 'flex', flexDirection: 'column', gap: '10px',
    }}>
      {/* Drop zone — warm dashed border */}
      <div
        onClick={() => !isUploading && inputRef.current?.click()}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        style={{
          padding: '18px 12px',
          borderRadius: 'var(--grimoire-radius)',
          border: `1px dashed ${
            isDragging
              ? 'var(--grimoire-gold)'
              : 'rgba(201, 177, 135, 0.22)'
          }`,
          background: isDragging
            ? 'rgba(201, 177, 135, 0.06)'
            : 'rgba(201, 177, 135, 0.02)',
          cursor: isUploading ? 'not-allowed' : 'pointer',
          transition: 'var(--grimoire-transition)',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '8px',
          textAlign: 'center',
        }}
        onMouseEnter={e => {
          if (!isUploading && !isDragging) {
            e.currentTarget.style.borderColor = 'rgba(201, 177, 135, 0.4)'
            e.currentTarget.style.background = 'rgba(201, 177, 135, 0.04)'
          }
        }}
        onMouseLeave={e => {
          if (!isUploading && !isDragging) {
            e.currentTarget.style.borderColor = 'rgba(201, 177, 135, 0.22)'
            e.currentTarget.style.background = 'rgba(201, 177, 135, 0.02)'
          }
        }}
      >
        {isUploading
          ? (
            <Loader2
              size={20}
              className="animate-spin"
              style={{ color: 'var(--grimoire-gold)' }}
            />
          )
          : (
            <Upload
              size={20}
              strokeWidth={1.5}
              style={{
                color: isDragging
                  ? 'var(--grimoire-gold-bright)'
                  : 'var(--grimoire-muted)',
              }}
            />
          )
        }
        <div style={{
          fontSize: '12.5px',
          fontWeight: 500,
          letterSpacing: '-0.1px',
          color: isDragging
            ? 'var(--grimoire-gold-soft)'
            : 'var(--grimoire-text-soft)',
        }}>
          {isUploading
            ? 'Indexing...'
            : isDragging
              ? 'Drop to ingest'
              : 'Drop file or click'}
        </div>
        <div
          title="Supported: PDF, markdown (.md), text, HTML, RST, source code (.py .js .ts .jsx .tsx .go .rs .java .cpp .c), config (.yaml .json .toml)"
          style={{
            fontSize: '10.5px',
            color: 'var(--grimoire-muted-2)',
            letterSpacing: '0.2px',
            cursor: 'help',
          }}
        >
          documents, code, and config files
        </div>
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.md,.markdown,.txt,.html,.htm,.rst,.py,.js,.ts,.jsx,.tsx,.go,.rs,.java,.cpp,.c,.yaml,.yml,.json,.toml"
          onChange={onChange}
          disabled={isUploading}
          style={{ display: 'none' }}
        />
      </div>

      {/* Status messages */}
      <AnimatePresence>
        {status.state === 'success' && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.38, ease: [0.4, 0, 0.2, 1] }}
            style={{
              padding: '7px 11px',
              borderRadius: 'var(--grimoire-radius-sm)',
              background: 'rgba(132, 169, 140, 0.08)',
              border: '1px solid rgba(132, 169, 140, 0.2)',
              fontSize: '11px',
              color: 'var(--grimoire-success)',
              display: 'flex', alignItems: 'center', gap: '7px',
              letterSpacing: '-0.1px',
            }}
          >
            <CheckCircle2 size={11} style={{ flexShrink: 0 }} strokeWidth={2} />
            <span style={{
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>
              Indexed {status.fileName}
            </span>
          </motion.div>
        )}

        {status.state === 'error' && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.38, ease: [0.4, 0, 0.2, 1] }}
            style={{
              padding: '7px 11px',
              borderRadius: 'var(--grimoire-radius-sm)',
              background: 'rgba(200, 123, 123, 0.08)',
              border: '1px solid rgba(200, 123, 123, 0.2)',
              fontSize: '11px',
              color: 'var(--grimoire-error)',
              display: 'flex', alignItems: 'center', gap: '7px',
              letterSpacing: '-0.1px',
            }}
          >
            <AlertCircle size={11} style={{ flexShrink: 0 }} strokeWidth={2} />
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {status.message}
            </span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Documents list — expandable */}
      {uniqueSources.length > 0 ? (
        <div>
          <button
            onClick={() => setExpanded(e => !e)}
            style={{
              width: '100%',
              display: 'flex', alignItems: 'center', gap: '7px',
              padding: '7px 10px',
              fontSize: '11px',
              color: 'var(--grimoire-muted)',
              background: 'transparent', border: 'none',
              cursor: 'pointer', textAlign: 'left',
              transition: 'color var(--grimoire-transition-fast)',
              fontFamily: 'inherit',
              letterSpacing: '-0.1px',
            }}
            onMouseEnter={e => { e.currentTarget.style.color = 'var(--grimoire-text-soft)' }}
            onMouseLeave={e => { e.currentTarget.style.color = 'var(--grimoire-muted)' }}
          >
            <FileText size={11} strokeWidth={1.8} />
            <span style={{ flex: 1 }}>
              {uniqueSources.length} document{uniqueSources.length > 1 ? 's' : ''} indexed
            </span>
            <motion.div
              animate={{ rotate: expanded ? 180 : 0 }}
              transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
            >
              <ChevronDown size={10} strokeWidth={1.8} />
            </motion.div>
          </button>

          <AnimatePresence>
            {expanded && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
                style={{ overflow: 'hidden' }}
              >
                <div style={{
                  display: 'flex', flexDirection: 'column', gap: '3px',
                  paddingLeft: '8px', paddingRight: '2px', marginTop: '4px',
                }}>
                  {uniqueSources.map((source, i) => {
                    // Alternate between gold and sage dot colors for variety
                    const dotColor = i % 2 === 0
                      ? 'var(--grimoire-gold)'
                      : 'var(--grimoire-sage)'
                    return (
                      <div
                        key={source}
                        style={{
                          display: 'flex', alignItems: 'center', gap: '8px',
                          padding: '6px 10px',
                          borderRadius: '7px',
                          background: 'rgba(201, 177, 135, 0.03)',
                          fontSize: '11.5px',
                          color: 'var(--grimoire-text-soft)',
                          transition: 'var(--grimoire-transition-fast)',
                          letterSpacing: '-0.1px',
                        }}
                        onMouseEnter={e => {
                          e.currentTarget.style.background = 'rgba(201, 177, 135, 0.07)'
                        }}
                        onMouseLeave={e => {
                          e.currentTarget.style.background = 'rgba(201, 177, 135, 0.03)'
                        }}
                      >
                        <span style={{
                          width: '5px', height: '5px',
                          borderRadius: '50%',
                          background: dotColor,
                          flexShrink: 0,
                        }} />
                        <span style={{
                          flex: 1, overflow: 'hidden',
                          textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                        }} title={source}>
                          {source}
                        </span>
                        <button
                          onClick={e => handleDelete(source, e)}
                          disabled={deleting === source}
                          title={`Delete ${source}`}
                          style={{
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            width: '18px', height: '18px',
                            borderRadius: '4px',
                            border: 'none', background: 'transparent',
                            color: 'var(--grimoire-muted-2)',
                            cursor: 'pointer',
                            flexShrink: 0,
                            transition: 'var(--grimoire-transition-fast)',
                            opacity: deleting === source ? 0.5 : 1,
                            fontFamily: 'inherit',
                          }}
                          onMouseEnter={e => {
                            e.currentTarget.style.color = 'var(--grimoire-error)'
                          }}
                          onMouseLeave={e => {
                            e.currentTarget.style.color = 'var(--grimoire-muted-2)'
                          }}
                        >
                          {deleting === source
                            ? <Loader2 size={10} className="animate-spin" />
                            : <X size={10} strokeWidth={2} />
                          }
                        </button>
                      </div>
                    )
                  })}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      ) : (
        <div style={{
          display: 'flex', alignItems: 'center', gap: '7px',
          padding: '7px 10px',
          fontSize: '11px',
          color: 'var(--grimoire-muted-2)',
          letterSpacing: '-0.1px',
        }}>
          <FileText size={11} strokeWidth={1.8} />
          <span>No documents yet</span>
        </div>
      )}
    </div>
  )
}