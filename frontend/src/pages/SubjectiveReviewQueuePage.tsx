import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { PenLine, Search, ChevronRight, CheckCircle2, Clock } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { PageLoading } from '@/components/shared/PageLoading'
import { usePendingSubjectiveReview } from '@/hooks/digitalExams'
import type { SubjectivePendingAttempt } from '@/types/digitalExam'

function formatDate(iso: string | null) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('en-IN', {
    day:    '2-digit',
    month:  'short',
    year:   'numeric',
    hour:   '2-digit',
    minute: '2-digit',
  })
}

function progressColor(scored: number, total: number) {
  if (total === 0) return 'bg-gray-200'
  if (scored === total) return 'bg-green-500'
  if (scored > 0) return 'bg-yellow-400'
  return 'bg-blue-400'
}

function AttemptCard({ item, onReview }: { item: SubjectivePendingAttempt; onReview: () => void }) {
  const allScored = item.scored_count === item.subjective_count
  const pct = item.subjective_count > 0
    ? Math.round((item.scored_count / item.subjective_count) * 100)
    : 0

  return (
    <div className="flex items-center justify-between rounded-lg border border-gray-200 bg-white p-4 shadow-sm hover:border-blue-300 transition-colors">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-3 mb-2">
          <span className="font-mono text-sm text-gray-600 truncate">
            {item.attempt_id.slice(0, 8).toUpperCase()}
          </span>
          {allScored ? (
            <Badge className="bg-green-100 text-green-800 text-xs">All Scored</Badge>
          ) : (
            <Badge className="bg-blue-100 text-blue-800 text-xs">Pending</Badge>
          )}
        </div>

        <div className="text-xs text-gray-500 mb-3">
          Submitted: {formatDate(item.submitted_at)}
        </div>

        <div className="flex items-center gap-4 text-sm">
          <span className="text-gray-600">
            MCQ: <span className="font-medium">{item.auto_score ?? 0} / {item.mcq_max_score ?? 0}</span>
          </span>
          <span className="text-gray-600">
            Subjective: <span className="font-medium">{item.scored_count}/{item.subjective_count}</span>
          </span>
        </div>

        <div className="mt-2 flex items-center gap-2">
          <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${progressColor(item.scored_count, item.subjective_count)}`}
              style={{ width: `${pct}%` }}
            />
          </div>
          <span className="text-xs text-gray-500 w-8 text-right">{pct}%</span>
        </div>
      </div>

      <Button
        size="sm"
        variant="ghost"
        onClick={onReview}
        className="ml-4 shrink-0 text-blue-600 hover:text-blue-700 hover:bg-blue-50"
      >
        Review
        <ChevronRight className="h-4 w-4 ml-1" />
      </Button>
    </div>
  )
}

function SessionQueue({ sessionId }: { sessionId: string }) {
  const navigate = useNavigate()
  const { data, isLoading, isError } = usePendingSubjectiveReview(sessionId)

  if (isLoading) return <PageLoading />

  if (isError) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-center">
        <p className="text-red-700 font-medium">Unable to load queue</p>
        <p className="text-sm text-red-600 mt-1">
          Check that session ID <code className="font-mono">{sessionId.slice(0, 8)}</code> is valid
          and you are assigned to this course.
        </p>
      </div>
    )
  }

  if (!data || data.items.length === 0) {
    return (
      <div className="rounded-lg border border-green-200 bg-green-50 p-10 text-center">
        <CheckCircle2 className="h-10 w-10 text-green-500 mx-auto mb-3" />
        <p className="text-green-800 font-medium text-lg">All caught up!</p>
        <p className="text-sm text-green-700 mt-1">
          No attempts are pending subjective review for this session.
        </p>
      </div>
    )
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="text-sm text-gray-600">
          <span className="font-medium text-gray-900">{data.total}</span> attempt{data.total !== 1 ? 's' : ''} pending review
        </div>
        <div className="text-xs text-gray-400 font-mono truncate max-w-[180px]">
          Session: {sessionId.slice(0, 8).toUpperCase()}…
        </div>
      </div>

      <div className="space-y-3">
        {data.items.map((item) => (
          <AttemptCard
            key={item.attempt_id}
            item={item}
            onReview={() =>
              navigate(`/faculty/digital-reviews/${item.attempt_id}?sessionId=${sessionId}`)
            }
          />
        ))}
      </div>
    </div>
  )
}

export default function SubjectiveReviewQueuePage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const initialSessionId = searchParams.get('sessionId') ?? ''
  const [inputValue, setInputValue] = useState(initialSessionId)
  const [activeSessionId, setActiveSessionId] = useState(initialSessionId)

  function handleLoad() {
    const trimmed = inputValue.trim()
    if (!trimmed) return
    setActiveSessionId(trimmed)
    setSearchParams({ sessionId: trimmed })
  }

  return (
    <div className="max-w-2xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="flex items-center gap-3 mb-8">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-600 text-white">
          <PenLine className="h-5 w-5" />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Subjective Review Queue</h1>
          <p className="text-sm text-gray-500">Score student subjective exam responses</p>
        </div>
      </div>

      {/* Session selector */}
      <div className="mb-6">
        <label className="block text-sm font-medium text-gray-700 mb-1.5">
          Session ID
        </label>
        <div className="flex gap-2">
          <Input
            placeholder="Paste session ID here…"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleLoad()}
            className="font-mono text-sm"
          />
          <Button onClick={handleLoad} disabled={!inputValue.trim()}>
            <Search className="h-4 w-4 mr-2" />
            Load Queue
          </Button>
        </div>
        <p className="mt-1.5 text-xs text-gray-500 flex items-center gap-1">
          <Clock className="h-3 w-3" />
          Ask your admin to share the session ID or link.
        </p>
      </div>

      {/* Results */}
      {activeSessionId && <SessionQueue sessionId={activeSessionId} />}
    </div>
  )
}
