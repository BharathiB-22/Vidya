/**
 * NotebookQA — Chat-style Q&A panel backed by M05 RAG endpoint.
 *
 * Props:
 *   packageId     — learning package UUID
 *   qdrantIndexed — whether the package has been RAG-indexed on the backend
 *
 * Behaviour:
 *   - On mount, loads the student's most-recent Q&A session (if any).
 *   - Subsequent questions are appended to that session (session_id forwarded).
 *   - Each assistant reply shows cited sources beneath it.
 *   - Input is disabled until the package is RAG-indexed.
 */

import { useEffect, useRef, useState } from 'react'
import { Bot, ExternalLink, Loader2, MessageCircle, Send, User } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useQASessions, useQASession, useAskQuestion } from '@/hooks/learningPackage'
import type { QARole, RAGSourceCitation } from '@/types/learningPackage'

// ---------------------------------------------------------------------------
// Local types
// ---------------------------------------------------------------------------

type LocalMessage = {
  id?: string
  role: QARole
  content: string
  sources: RAGSourceCitation[]
  isLoading?: boolean
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function TypingDots() {
  return (
    <div className="flex gap-1 items-center py-1 px-0.5">
      <span className="h-1.5 w-1.5 rounded-full bg-gray-400 animate-bounce [animation-delay:-0.3s]" />
      <span className="h-1.5 w-1.5 rounded-full bg-gray-400 animate-bounce [animation-delay:-0.15s]" />
      <span className="h-1.5 w-1.5 rounded-full bg-gray-400 animate-bounce" />
    </div>
  )
}

function SourceList({ sources }: { sources: RAGSourceCitation[] }) {
  if (sources.length === 0) return null
  return (
    <div className="mt-2.5 pt-2 border-t border-gray-100 space-y-1.5">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-600">
        Sources
      </p>
      {sources.map((src) => (
        <div key={src.item_id} className="flex items-start gap-1.5 text-xs text-gray-500">
          <ExternalLink className="h-3 w-3 mt-0.5 shrink-0 text-gray-500" />
          <div className="min-w-0">
            {src.url ? (
              <a
                href={src.url}
                target="_blank"
                rel="noopener noreferrer"
                className="font-medium text-blue-600 hover:underline underline-offset-2 line-clamp-1"
              >
                {src.title}
              </a>
            ) : (
              <span className="font-medium text-gray-700 line-clamp-1">{src.title}</span>
            )}
            {src.snippet && (
              <p className="text-gray-600 line-clamp-2 mt-0.5">{src.snippet}</p>
            )}
          </div>
          {src.relevance_score !== null && (
            <span className="ml-auto shrink-0 tabular-nums text-gray-500">
              {Math.round(src.relevance_score * 100)}%
            </span>
          )}
        </div>
      ))}
    </div>
  )
}

function MessageBubble({ msg }: { msg: LocalMessage }) {
  const isUser = msg.role === 'USER'
  return (
    <div className={`flex gap-2.5 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
      {/* Avatar */}
      <div
        className={`h-7 w-7 rounded-full flex items-center justify-center shrink-0 mt-0.5 ${
          isUser ? 'bg-blue-100' : 'bg-gray-100'
        }`}
      >
        {isUser ? (
          <User className="h-3.5 w-3.5 text-blue-600" />
        ) : (
          <Bot className="h-3.5 w-3.5 text-gray-500" />
        )}
      </div>

      {/* Bubble */}
      <div
        className={`max-w-[80%] rounded-xl px-3.5 py-2.5 text-sm ${
          isUser
            ? 'bg-blue-600 text-white rounded-tr-sm'
            : 'bg-gray-50 border border-gray-100 text-gray-800 rounded-tl-sm'
        }`}
      >
        {msg.isLoading ? (
          <TypingDots />
        ) : (
          <p className="whitespace-pre-wrap leading-relaxed">{msg.content}</p>
        )}
        {!isUser && !msg.isLoading && <SourceList sources={msg.sources} />}
      </div>
    </div>
  )
}

function InitSkeleton() {
  return (
    <div className="space-y-4 animate-pulse">
      <div className="flex gap-2.5 flex-row-reverse">
        <div className="h-7 w-7 rounded-full bg-blue-100 shrink-0" />
        <div className="h-9 w-48 rounded-xl bg-blue-50" />
      </div>
      <div className="flex gap-2.5">
        <div className="h-7 w-7 rounded-full bg-gray-100 shrink-0" />
        <div className="h-16 w-64 rounded-xl bg-gray-100" />
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function NotebookQA({
  packageId,
  qdrantIndexed,
}: {
  packageId: string
  qdrantIndexed: boolean
}) {
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [messages, setMessages]               = useState<LocalMessage[]>([])
  const [initialized, setInitialized]         = useState(false)
  const [inputText, setInputText]             = useState('')
  const [askError, setAskError]               = useState<string | null>(null)
  const bottomRef                             = useRef<HTMLDivElement>(null)

  // ── Data queries ──────────────────────────────────────────────────────────
  const { data: sessions, isLoading: sessionsLoading, isError: sessionsError } =
    useQASessions(packageId)
  const { data: sessionData, isLoading: sessionLoading, isError: sessionError } =
    useQASession(packageId, activeSessionId ?? '')
  const askMutation = useAskQuestion(packageId)

  // ── Initialization: pick up most-recent session ───────────────────────────
  // History is a convenience, not a precondition: if the session queries fail
  // we still initialize, so the composer stays usable instead of being locked
  // behind a permanent "Loading session…" state.
  useEffect(() => {
    if (initialized) return
    if (sessionsLoading) return
    if (sessionsError || !sessions) {
      setInitialized(true)
      return
    }
    if (sessions.length > 0) {
      setActiveSessionId(sessions[0].id)
    } else {
      setInitialized(true)
    }
  }, [sessions, sessionsLoading, sessionsError, initialized])

  useEffect(() => {
    if (initialized) return
    if (!activeSessionId) return
    if (sessionLoading) return
    if (sessionError) {
      setInitialized(true)
      return
    }
    if (sessionData) {
      setMessages(
        sessionData.messages.map((m) => ({
          id:      m.id,
          role:    m.role,
          content: m.content,
          sources: m.sources,
        })),
      )
      setInitialized(true)
    }
  }, [sessionData, sessionLoading, sessionError, activeSessionId, initialized])

  // ── Auto-scroll on new message ────────────────────────────────────────────
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // ── Submit handler ────────────────────────────────────────────────────────
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const question = inputText.trim()
    if (!question || askMutation.isPending) return

    setInputText('')
    setAskError(null)

    setMessages((prev) => [
      ...prev,
      { role: 'USER',      content: question, sources: []          },
      { role: 'ASSISTANT', content: '',        sources: [], isLoading: true },
    ])

    try {
      const result = await askMutation.mutateAsync({
        question,
        sessionId: activeSessionId ?? undefined,
      })

      setActiveSessionId(result.session_id)
      setMessages((prev) => [
        ...prev.slice(0, -1),
        {
          id:      result.message_id,
          role:    'ASSISTANT' as QARole,
          content: result.answer,
          sources: result.sources,
        },
      ])
    } catch (err) {
      setMessages((prev) => prev.slice(0, -1))

      // If the backend reports the session is gone (e.g. server restarted,
      // or a prior request's commit failed), reset activeSessionId so the
      // next question creates a fresh session rather than failing again.
      const errCode = (err as { response?: { data?: { detail?: { error?: string } } } })
        ?.response?.data?.detail?.error
      if (errCode === 'SESSION_NOT_FOUND' || errCode === 'RAG_ERROR') {
        setActiveSessionId(null)
      }

      setAskError('Failed to get an answer. Please try again.')
    }
  }

  // ── Derived ───────────────────────────────────────────────────────────────
  const isInitializing = !initialized
  const canAsk = qdrantIndexed && !isInitializing && !askMutation.isPending

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">

      {/* ── Header ── */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-100 bg-gray-50/60">
        <MessageCircle className="h-4 w-4 text-blue-500 shrink-0" />
        <h2 className="text-sm font-semibold text-gray-800">Ask about this package</h2>
        {!qdrantIndexed && (
          <span className="ml-auto text-xs text-amber-600 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full">
            RAG indexing pending
          </span>
        )}
      </div>

      {/* ── Messages ── */}
      <div className="h-80 overflow-y-auto px-4 py-4 space-y-4">
        {isInitializing ? (
          <InitSkeleton />
        ) : messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-2 text-gray-500">
            <MessageCircle className="h-8 w-8" />
            <p className="text-sm text-gray-600">
              {qdrantIndexed
                ? 'Ask a question about the learning materials.'
                : 'Q&A will be available once RAG indexing completes.'}
            </p>
          </div>
        ) : (
          messages.map((msg, i) => <MessageBubble key={msg.id ?? i} msg={msg} />)
        )}
        <div ref={bottomRef} />
      </div>

      {/* ── Input ── */}
      <div className="px-4 py-3 border-t border-gray-100">
        <form onSubmit={handleSubmit} className="flex gap-2">
          <input
            type="text"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            disabled={!canAsk}
            placeholder={
              !qdrantIndexed
                ? 'Waiting for RAG indexing…'
                : isInitializing
                ? 'Loading session…'
                : 'Ask a question about this package…'
            }
            className="flex-1 rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-800 placeholder-gray-300 outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-100 disabled:bg-gray-50 disabled:text-gray-600 transition-colors"
          />
          <Button
            type="submit"
            size="sm"
            disabled={!canAsk || !inputText.trim()}
            className="shrink-0 px-3"
          >
            {askMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </Button>
        </form>
        {askError && (
          <p className="mt-1.5 text-xs text-red-500">{askError}</p>
        )}
      </div>
    </div>
  )
}
