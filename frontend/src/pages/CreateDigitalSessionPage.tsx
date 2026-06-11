// M09.5 Admin — Create Digital Exam Session
import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ChevronLeft, Monitor, Loader2, AlertCircle, FileText, PlusCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { useCreateSession } from '@/hooks/digitalExams'
import { listAllExamPapers } from '@/lib/api/exam'
import { getErrorMessage } from '@/lib/api'
import type { ExamPaper } from '@/types/exam'

const READY_STATUSES = new Set(['BOARD_APPROVED', 'SEALED', 'RELEASED'])

export default function CreateDigitalSessionPage() {
  const navigate = useNavigate()

  const { data: papersData, isLoading: papersLoading } = useQuery({
    queryKey: ['exam-papers-all'],
    queryFn: () => listAllExamPapers({ limit: 200 }),
  })

  const readyPapers: ExamPaper[] = (papersData?.items ?? []).filter(p =>
    READY_STATUSES.has(p.status),
  )

  const [paperId,   setPaperId]   = useState('')
  const [title,     setTitle]     = useState('')
  const [duration,  setDuration]  = useState(60)
  const [winStart,  setWinStart]  = useState('')
  const [winEnd,    setWinEnd]    = useState('')
  const [instr,     setInstr]     = useState('')
  const [error,     setError]     = useState('')

  // Auto-fill title when paper is selected
  useEffect(() => {
    if (paperId) {
      const paper = readyPapers.find(p => p.id === paperId)
      if (paper && !title) setTitle(paper.title)
    }
  }, [paperId]) // eslint-disable-line react-hooks/exhaustive-deps

  const { mutate: create, isPending } = useCreateSession()

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    if (!paperId) { setError('Select an exam paper.'); return }
    if (!title.trim()) { setError('Title is required.'); return }
    if (duration < 5 || duration > 480) { setError('Duration must be 5–480 minutes.'); return }

    create(
      {
        exam_paper_id: paperId,
        title: title.trim(),
        max_duration_mins: duration,
        window_start: winStart || null,
        window_end:   winEnd   || null,
        instructions: instr.trim() || null,
      },
      {
        onSuccess: (session) => navigate(`/exams/digital/${session.id}`),
        onError:   (err)     => setError(getErrorMessage(err)),
      },
    )
  }

  return (
    <PageShell>
      <PageHeader
        icon={PlusCircle}
        title="New Digital Exam Session"
        subtitle="Configure an online delivery session linked to a sealed exam paper"
      />

      <div className="max-w-2xl space-y-6">
        <Button
          variant="ghost"
          size="sm"
          className="-ml-1 mb-2"
          onClick={() => navigate('/exams/digital')}
        >
          <ChevronLeft className="h-4 w-4 mr-1" />
          Back to Sessions
        </Button>

        <form onSubmit={handleSubmit} className="space-y-5">
          {/* Exam Paper */}
          <div className="rounded-xl border border-gray-200 bg-white px-5 py-4 space-y-4">
            <h2 className="text-sm font-semibold text-gray-800 flex items-center gap-2">
              <FileText className="h-4 w-4 text-indigo-500" />
              Exam Paper
            </h2>

            {papersLoading ? (
              <div className="flex items-center gap-2 text-sm text-gray-400">
                <Loader2 className="h-4 w-4 animate-spin" /> Loading papers…
              </div>
            ) : readyPapers.length === 0 ? (
              <p className="text-sm text-amber-600">
                No approved/sealed papers available. Seal a paper first.
              </p>
            ) : (
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-gray-600">
                  Select paper <span className="text-red-500">*</span>
                </label>
                <select
                  value={paperId}
                  onChange={e => setPaperId(e.target.value)}
                  className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 bg-white"
                >
                  <option value="">— choose paper —</option>
                  {readyPapers.map(p => (
                    <option key={p.id} value={p.id}>
                      {p.title} ({p.status})
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>

          {/* Session Details */}
          <div className="rounded-xl border border-gray-200 bg-white px-5 py-4 space-y-4">
            <h2 className="text-sm font-semibold text-gray-800 flex items-center gap-2">
              <Monitor className="h-4 w-4 text-indigo-500" />
              Session Details
            </h2>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-gray-600">
                Session title <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={title}
                onChange={e => setTitle(e.target.value)}
                placeholder="e.g. End Sem — CS101 — Dec 2026"
                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-gray-600">
                Duration (minutes) <span className="text-red-500">*</span>
              </label>
              <input
                type="number"
                min={5}
                max={480}
                value={duration}
                onChange={e => setDuration(Number(e.target.value))}
                className="w-40 rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
              />
            </div>
          </div>

          {/* Exam Window */}
          <div className="rounded-xl border border-gray-200 bg-white px-5 py-4 space-y-4">
            <h2 className="text-sm font-semibold text-gray-800">
              Exam Window <span className="text-gray-400 font-normal">(optional)</span>
            </h2>
            <p className="text-xs text-gray-500">
              Set start and end times to restrict when students can enter the session.
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-gray-600">Window opens</label>
                <input
                  type="datetime-local"
                  value={winStart}
                  onChange={e => setWinStart(e.target.value)}
                  className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-gray-600">Window closes</label>
                <input
                  type="datetime-local"
                  value={winEnd}
                  onChange={e => setWinEnd(e.target.value)}
                  className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
                />
              </div>
            </div>
          </div>

          {/* Instructions */}
          <div className="rounded-xl border border-gray-200 bg-white px-5 py-4 space-y-3">
            <h2 className="text-sm font-semibold text-gray-800">
              Instructions <span className="text-gray-400 font-normal">(optional)</span>
            </h2>
            <textarea
              rows={4}
              value={instr}
              onChange={e => setInstr(e.target.value)}
              placeholder="Any specific instructions shown to students before they start…"
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 resize-none"
            />
          </div>

          {/* Error */}
          {error && (
            <div className="flex items-start gap-2 rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
              <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
              {error}
            </div>
          )}

          {/* Actions */}
          <div className="flex gap-3">
            <Button type="submit" disabled={isPending || papersLoading}>
              {isPending ? (
                <><Loader2 className="h-4 w-4 animate-spin mr-1.5" />Creating…</>
              ) : (
                'Create Session'
              )}
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => navigate('/exams/digital')}
            >
              Cancel
            </Button>
          </div>
        </form>
      </div>
    </PageShell>
  )
}
