'use client'
import { useState, useRef, DragEvent, ChangeEvent } from 'react'
import { Upload, FileText, CheckCircle2, AlertCircle, Loader2, X, ChevronDown } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { deleteSource } from '@/lib/api'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface UploadPanelProps {
  totalChunks: number
  uniqueSources?: string[]
  onIngestComplete: () => void
}

type UploadStatus =
  | { state: 'idle' }
  | { state: 'uploading'; fileName: string }
  | { state: 'success'; fileName: string; chunks: number }
  | { state: 'error'; message: string }

export function UploadPanel({ totalChunks, uniqueSources = [], onIngestComplete }: UploadPanelProps) {
  const [isDragging, setIsDragging] = useState(false)
  const [status, setStatus] = useState<UploadStatus>({ state: 'idle' })
  const [expanded, setExpanded] = useState(false)
  const [deleting, setDeleting] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleDelete = async (source: string, e: React.MouseEvent) => {
    e.stopPropagation()
    if (deleting) return
    setDeleting(source)
    try {
      await deleteSource(source)
      onIngestComplete() // refreshes the list
    } catch {
      // ignore - the list will refresh anyway
    } finally {
      setDeleting(null)
    }
  }

  const handleFiles = async (files: FileList | null) => {
    if (!files || files.length === 0) return

    const file = files[0]
    setStatus({ state: 'uploading', fileName: file.name })

    const formData = new FormData()
    formData.append('file', file)

    try {
      // 5 minute timeout for large files
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

      // Auto-clear success after 3 seconds
      setTimeout(() => setStatus({ state: 'idle' }), 3000)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Upload failed'
      setStatus({ state: 'error', message: msg })
      setTimeout(() => setStatus({ state: 'idle' }), 5000)
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
    <div style={{ padding: '12px 12px 0', display: 'flex', flexDirection: 'column', gap: '8px' }}>
      <div
        onClick={() => !isUploading && inputRef.current?.click()}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        style={{
          padding: '14px 12px',
          borderRadius: '10px',
          border: `1.5px dashed ${
            isDragging
              ? 'var(--grimoire-violet)'
              : isUploading
                ? 'var(--grimoire-border-hover)'
                : 'var(--grimoire-border)'
          }`,
          background: isDragging
            ? 'rgba(139,92,246,0.08)'
            : 'rgba(139,92,246,0.02)',
          cursor: isUploading ? 'not-allowed' : 'pointer',
          transition: 'all 0.2s',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '6px',
          textAlign: 'center',
        }}
        onMouseEnter={e => {
          if (!isUploading && !isDragging) {
            e.currentTarget.style.borderColor = 'var(--grimoire-border-hover)'
            e.currentTarget.style.background = 'rgba(139,92,246,0.05)'
          }
        }}
        onMouseLeave={e => {
          if (!isUploading && !isDragging) {
            e.currentTarget.style.borderColor = 'var(--grimoire-border)'
            e.currentTarget.style.background = 'rgba(139,92,246,0.02)'
          }
        }}
      >
        {isUploading
          ? <Loader2 size={18} className="animate-spin" style={{ color: 'var(--grimoire-violet)' }} />
          : <Upload size={18} style={{ color: isDragging ? 'var(--grimoire-violet)' : 'var(--grimoire-muted)' }} />
        }
        <span style={{
          fontSize: '12px',
          color: isDragging ? 'var(--grimoire-violet-bright)' : 'var(--grimoire-muted)',
          fontWeight: 500,
        }}>
          {isUploading
            ? 'Ingesting...'
            : isDragging
              ? 'Drop to ingest'
              : 'Drop file or click'}
        </span>
        <span style={{ fontSize: '10px', color: 'var(--grimoire-muted)' }}>
          .md .txt .py .js .ts .pdf .html
        </span>
        <input
          ref={inputRef}
          type="file"
          accept=".md,.txt,.py,.js,.ts,.jsx,.tsx,.pdf,.html,.rst,.yaml,.json,.go,.rs,.java,.cpp,.c"
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
            style={{
              padding: '6px 10px', borderRadius: '6px',
              background: 'rgba(34,197,94,0.08)',
              border: '1px solid rgba(34,197,94,0.2)',
              fontSize: '11px', color: '#86efac',
              display: 'flex', alignItems: 'center', gap: '6px',
            }}
          >
            <CheckCircle2 size={11} style={{ flexShrink: 0 }} />
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              Indexed {status.fileName}
            </span>
          </motion.div>
        )}

        {status.state === 'error' && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            style={{
              padding: '6px 10px', borderRadius: '6px',
              background: 'rgba(239,68,68,0.08)',
              border: '1px solid rgba(239,68,68,0.2)',
              fontSize: '11px', color: '#fca5a5',
              display: 'flex', alignItems: 'center', gap: '6px',
            }}
          >
            <AlertCircle size={11} style={{ flexShrink: 0 }} />
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {status.message}
            </span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Collection stats — expandable list */}
      {uniqueSources.length > 0 ? (
        <div>
          <button
            onClick={() => setExpanded(e => !e)}
            style={{
              width: '100%',
              display: 'flex', alignItems: 'center', gap: '6px',
              padding: '6px 10px', fontSize: '11px',
              color: 'var(--grimoire-muted)',
              background: 'transparent', border: 'none',
              cursor: 'pointer', textAlign: 'left',
              transition: 'color 0.15s',
            }}
            onMouseEnter={e => { e.currentTarget.style.color = 'var(--grimoire-text)' }}
            onMouseLeave={e => { e.currentTarget.style.color = 'var(--grimoire-muted)' }}
          >
            <FileText size={11} />
            <span style={{ flex: 1 }}>
              {uniqueSources.length} document{uniqueSources.length > 1 ? 's' : ''} indexed
            </span>
            <motion.div animate={{ rotate: expanded ? 180 : 0 }} transition={{ duration: 0.2 }}>
              <ChevronDown size={10} />
            </motion.div>
          </button>

          <AnimatePresence>
            {expanded && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.2 }}
                style={{ overflow: 'hidden' }}
              >
                <div style={{
                  display: 'flex', flexDirection: 'column', gap: '2px',
                  paddingLeft: '10px', paddingRight: '4px', marginTop: '2px',
                }}>
                  {uniqueSources.map(source => (
                    <div
                      key={source}
                      style={{
                        display: 'flex', alignItems: 'center', gap: '6px',
                        padding: '5px 8px', borderRadius: '6px',
                        background: 'rgba(139,92,246,0.04)',
                        fontSize: '11px', color: 'var(--grimoire-muted)',
                        transition: 'all 0.15s',
                      }}
                      onMouseEnter={e => { e.currentTarget.style.background = 'rgba(139,92,246,0.08)' }}
                      onMouseLeave={e => { e.currentTarget.style.background = 'rgba(139,92,246,0.04)' }}
                    >
                      <FileText size={9} style={{ flexShrink: 0 }} />
                      <span style={{
                        flex: 1, overflow: 'hidden',
                        textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      }}
                        title={source}
                      >
                        {source}
                      </span>
                      <button
                        onClick={e => handleDelete(source, e)}
                        disabled={deleting === source}
                        title={`Delete ${source}`}
                        style={{
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          width: '16px', height: '16px', borderRadius: '4px',
                          border: 'none', background: 'transparent',
                          color: 'var(--grimoire-muted)', cursor: 'pointer',
                          flexShrink: 0, transition: 'all 0.15s',
                          opacity: deleting === source ? 0.5 : 1,
                        }}
                        onMouseEnter={e => { e.currentTarget.style.color = '#f87171' }}
                        onMouseLeave={e => { e.currentTarget.style.color = 'var(--grimoire-muted)' }}
                      >
                        {deleting === source
                          ? <Loader2 size={9} className="animate-spin" />
                          : <X size={9} />
                        }
                      </button>
                    </div>
                  ))}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      ) : (
        <div style={{
          display: 'flex', alignItems: 'center', gap: '6px',
          padding: '6px 10px', fontSize: '11px',
          color: 'var(--grimoire-muted)',
        }}>
          <FileText size={11} />
          <span>No documents yet</span>
        </div>
      )}
    </div>
  )
}