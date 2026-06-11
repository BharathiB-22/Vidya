import { useState, useEffect } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import {
  ChevronLeft,
  PenLine,
  CheckCircle2,
  Circle,
  Save,
  Send,
  AlertTriangle,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { PageLoading } from '@/components/shared/PageLoading'
import { addToast } from '@/hooks/useToast'
import { useSubjectiveResponses, useSaveFacultyScore, useSubmitSubjectiveScores } from '@/hooks/digitalExams'
import type { SubjectiveResponseItem } from '@/types/digitalExam'

type LocalScore = { score: string; note: string }

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

function ResponseCard({
  item,
  index,
  local,
  onChange,
  onSave,
  saving,
}: {
  item:     SubjectiveResponseItem
  index:    number
  local:    LocalScore
  onChange: (field: 'score' | 'note', value: string) => void
  onSave:   () => void
  saving:   boolean
}) {
  const isScored        = item.faculty_score !== null && item.faculty_score !== undefined
  const scoreNum        = parseFloat(local.score)
  const valid           = !isNaN(scoreNum) && scoreNum >= 0 && scoreNum <= item.max_marks
  const dirty           = !isScored
    || String(item.faculty_score) !== local.score
    || (item.faculty_note ?? '') !== local.note

  return (
    <div className={`rounded-lg border bg-white shadow-sm overflow-hidden ${isScored ? 'border-green-200' : 'border-gray-200'}`}>
      {/* Card header */}
      <div className={`flex items-center justify-between px-4 py-2.5 ${isScored ? 'bg-green-50' : 'bg-gray-50'} border-b`}>
        <div className="flex items-center gap-2">
          {isScored ? (
            <CheckCircle2 className="h-4 w-4 text-green-600 shrink-0" />
          ) : (
            <Circle className="h-4 w-4 text-gray-400 shrink-0" />
          )}
          <span className="text-sm font-medium text-gray-700">
            Question {index + 1}
          </span>
        </div>
        <span className="text-xs text-gray-500">Max: {item.max_marks} mark{item.max_marks !== 1 ? 's' : ''}</span>
      </div>

      <div className="p-4 space-y-4">
        {/* Question text */}
        <div>
          <p className="text-xs uppercase tracking-wide text-gray-400 mb-1">Question</p>
          <p className="text-sm text-gray-900 leading-relaxed">{item.question_text}</p>
        </div>

        {/* Student response */}
        <div>
          <p className="text-xs uppercase tracking-wide text-gray-400 mb-1">Student Response</p>
          {item.response_text ? (
            <div className="rounded-md border border-gray-100 bg-gray-50 p-3 text-sm text-gray-800 leading-relaxed whitespace-pre-wrap">
              {item.response_text}
            </div>
          ) : (
            <p className="text-sm text-gray-400 italic">No response provided</p>
          )}
        </div>

        {/* Scoring */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Score (0 – {item.max_marks})
            </label>
            <Input
              type="number"
              min={0}
              max={item.max_marks}
              step={0.5}
              value={local.score}
              onChange={(e) => onChange('score', e.target.value)}
              className={`text-sm ${!valid && local.score !== '' ? 'border-red-400' : ''}`}
              placeholder="0"
            />
            {!valid && local.score !== '' && (
              <p className="text-xs text-red-500 mt-0.5">
                Must be 0 – {item.max_marks}
              </p>
            )}
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Note (optional)
            </label>
            <Input
              value={local.note}
              onChange={(e) => onChange('note', e.target.value)}
              placeholder="Feedback for student…"
              className="text-sm"
            />
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between pt-1">
          <div className="text-xs text-gray-400">
            {isScored && !dirty && (
              <span className="text-green-600 font-medium">
                Saved — {item.faculty_scored_at ? formatDate(item.faculty_scored_at) : ''}
              </span>
            )}
          </div>
          <Button
            size="sm"
            onClick={onSave}
            disabled={!valid || local.score === '' || saving || !dirty}
            variant={isScored && !dirty ? 'outline' : 'default'}
          >
            {saving ? (
              <>Saving…</>
            ) : isScored && !dirty ? (
              <><CheckCircle2 className="h-3.5 w-3.5 mr-1" />Saved</>
            ) : (
              <><Save className="h-3.5 w-3.5 mr-1" />Save</>
            )}
          </Button>
        </div>
      </div>
    </div>
  )
}

export default function SubjectiveReviewPage() {
  const { attemptId = '' }     = useParams<{ attemptId: string }>()
  const [searchParams]         = useSearchParams()
  const sessionId              = searchParams.get('sessionId') ?? ''
  const navigate               = useNavigate()

  const { data, isLoading, isError } = useSubjectiveResponses(attemptId)
  const saveScore  = useSaveFacultyScore()
  const submitAll  = useSubmitSubjectiveScores()

  const [localScores, setLocalScores] = useState<Record<string, LocalScore>>({})
  const [savingQid, setSavingQid]     = useState<string | null>(null)
  const [confirmOpen, setConfirmOpen] = useState(false)

  // Initialise local state from server data
  useEffect(() => {
    if (!data) return
    const init: Record<string, LocalScore> = {}
    data.responses.forEach((r) => {
      init[r.question_id] = {
        score: r.faculty_score !== null && r.faculty_score !== undefined
          ? String(r.faculty_score)
          : '',
        note: r.faculty_note ?? '',
      }
    })
    setLocalScores((prev) => {
      // Only seed fields not yet touched
      const merged = { ...init }
      Object.keys(prev).forEach((k) => {
        merged[k] = prev[k]
      })
      return merged
    })
  }, [data])

  function handleChange(qid: string, field: 'score' | 'note', value: string) {
    setLocalScores((prev) => ({
      ...prev,
      [qid]: { ...(prev[qid] ?? { score: '', note: '' }), [field]: value },
    }))
  }

  async function handleSave(item: SubjectiveResponseItem) {
    const local = localScores[item.question_id]
    if (!local) return
    const score = parseFloat(local.score)
    if (isNaN(score) || score < 0 || score > item.max_marks) return

    setSavingQid(item.question_id)
    try {
      await saveScore.mutateAsync({
        attemptId,
        questionId: item.question_id,
        payload: { score, note: local.note || null },
      })
      addToast('Score saved', 'success', 2500)
    } catch {
      addToast('Failed to save score', 'error', 4000)
    } finally {
      setSavingQid(null)
    }
  }

  async function handleSubmit() {
    setConfirmOpen(false)
    try {
      await submitAll.mutateAsync({ attemptId, payload: { confirm: true } })
      addToast('Evaluation submitted successfully', 'success', 4000)
      navigate(sessionId ? `/faculty/digital-reviews?sessionId=${sessionId}` : '/faculty/digital-reviews')
    } catch {
      addToast('Submission failed. Ensure all responses are scored.', 'error', 5000)
    }
  }

  if (isLoading) return <PageLoading />

  if (isError || !data) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-8">
        <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-center">
          <AlertTriangle className="h-8 w-8 text-red-500 mx-auto mb-2" />
          <p className="text-red-700 font-medium">Unable to load attempt</p>
          <p className="text-sm text-red-600 mt-1">
            Check your access or try again.
          </p>
        </div>
      </div>
    )
  }

  const progressPct = data.total_subjective > 0
    ? Math.round((data.scored_count / data.total_subjective) * 100)
    : 0

  const backPath = sessionId
    ? `/faculty/digital-reviews?sessionId=${sessionId}`
    : '/faculty/digital-reviews'

  return (
    <div className="max-w-2xl mx-auto px-4 py-8">
      {/* Back nav */}
      <button
        onClick={() => navigate(backPath)}
        className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-800 mb-6 transition-colors"
      >
        <ChevronLeft className="h-4 w-4" />
        Back to Queue
      </button>

      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-600 text-white">
            <PenLine className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-gray-900">
              Review Attempt
            </h1>
            <p className="text-sm text-gray-500 font-mono">
              {attemptId.slice(0, 8).toUpperCase()}
            </p>
          </div>
        </div>

        <Badge
          className={
            data.status === 'FULLY_EVALUATED'
              ? 'bg-green-100 text-green-800'
              : 'bg-blue-100 text-blue-800'
          }
        >
          {data.status.replace('_', ' ')}
        </Badge>
      </div>

      {/* Stats strip */}
      <div className="grid grid-cols-3 gap-3 mb-6">
        <div className="rounded-lg border bg-white p-3 text-center">
          <p className="text-xs text-gray-500 mb-0.5">MCQ Score</p>
          <p className="text-lg font-semibold text-gray-900">
            {data.auto_score ?? 0}
            <span className="text-sm font-normal text-gray-400"> / {data.mcq_max_score ?? 0}</span>
          </p>
        </div>
        <div className="rounded-lg border bg-white p-3 text-center">
          <p className="text-xs text-gray-500 mb-0.5">Subjective</p>
          <p className="text-lg font-semibold text-gray-900">
            {data.scored_count}
            <span className="text-sm font-normal text-gray-400"> / {data.total_subjective}</span>
          </p>
        </div>
        <div className="rounded-lg border bg-white p-3 text-center">
          <p className="text-xs text-gray-500 mb-0.5">Submitted</p>
          <p className="text-sm font-medium text-gray-700">
            {data.submitted_at ? formatDate(data.submitted_at) : '—'}
          </p>
        </div>
      </div>

      {/* Progress bar */}
      <div className="mb-6">
        <div className="flex justify-between text-xs text-gray-500 mb-1.5">
          <span>Scoring progress</span>
          <span>{data.scored_count} of {data.total_subjective} scored</span>
        </div>
        <div className="h-2 w-full bg-gray-100 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${progressPct === 100 ? 'bg-green-500' : 'bg-blue-500'}`}
            style={{ width: `${progressPct}%` }}
          />
        </div>
      </div>

      {/* Response cards */}
      <div className="space-y-4 mb-8">
        {data.responses.map((item, idx) => (
          <ResponseCard
            key={item.question_id}
            item={item}
            index={idx}
            local={localScores[item.question_id] ?? { score: '', note: '' }}
            onChange={(field, value) => handleChange(item.question_id, field, value)}
            onSave={() => handleSave(item)}
            saving={savingQid === item.question_id}
          />
        ))}
      </div>

      {/* Submit evaluation */}
      {data.status !== 'FULLY_EVALUATED' && (
        <div className={`rounded-lg border p-4 ${data.all_scored ? 'border-green-200 bg-green-50' : 'border-gray-200 bg-gray-50'}`}>
          <div className="flex items-center justify-between">
            <div>
              <p className={`text-sm font-medium ${data.all_scored ? 'text-green-800' : 'text-gray-600'}`}>
                {data.all_scored
                  ? 'All responses scored — ready to submit'
                  : `${data.total_subjective - data.scored_count} response${data.total_subjective - data.scored_count !== 1 ? 's' : ''} remaining`}
              </p>
              <p className="text-xs text-gray-500 mt-0.5">
                Submitting finalises the evaluation and cannot be undone.
              </p>
            </div>
            <Button
              onClick={() => setConfirmOpen(true)}
              disabled={!data.all_scored || submitAll.isPending}
              className="ml-4 shrink-0 bg-green-600 hover:bg-green-700 text-white"
            >
              <Send className="h-4 w-4 mr-2" />
              {submitAll.isPending ? 'Submitting…' : 'Submit Evaluation'}
            </Button>
          </div>
        </div>
      )}

      {data.status === 'FULLY_EVALUATED' && (
        <div className="rounded-lg border border-green-200 bg-green-50 p-4 text-center">
          <CheckCircle2 className="h-8 w-8 text-green-500 mx-auto mb-2" />
          <p className="text-green-800 font-medium">Evaluation complete</p>
          <p className="text-sm text-green-700 mt-0.5">
            This attempt has been fully evaluated.
          </p>
        </div>
      )}

      {/* Confirm dialog */}
      <ConfirmDialog
        open={confirmOpen}
        title="Submit Evaluation"
        description={`You are about to finalise the evaluation for attempt ${attemptId.slice(0, 8).toUpperCase()}. This action cannot be undone.`}
        confirmLabel="Submit"
        onConfirm={handleSubmit}
        onCancel={() => setConfirmOpen(false)}
        loading={submitAll.isPending}
      />
    </div>
  )
}
