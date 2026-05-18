// M08 Exam Setter — Faculty: create exam paper configuration form
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { FileText, Loader2, ChevronLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { createExamPaper } from '@/lib/api/exam'
import type { BloomsDistribution, ExamPaperCreatePayload, ExamType, QuestionFormatConfig } from '@/types/exam'

const BLOOM_LEVELS: Array<{ key: keyof BloomsDistribution; label: string; color: string }> = [
  { key: 'remember',   label: 'Remember',   color: 'bg-red-400' },
  { key: 'understand', label: 'Understand', color: 'bg-orange-400' },
  { key: 'apply',      label: 'Apply',      color: 'bg-yellow-400' },
  { key: 'analyse',    label: 'Analyse',    color: 'bg-green-400' },
  { key: 'evaluate',   label: 'Evaluate',   color: 'bg-blue-400' },
  { key: 'create',     label: 'Create',     color: 'bg-purple-400' },
]

const EXAM_TYPES: ExamType[] = ['END_SEM', 'MID_SEM', 'QUIZ', 'INTERNAL', 'CUSTOM']

const DEFAULT_DIST: BloomsDistribution = {
  remember: 20, understand: 20, apply: 20, analyse: 20, evaluate: 10, create: 10,
}

const DEFAULT_FORMAT: QuestionFormatConfig = {
  mcq_count: 5, short_count: 3, long_count: 2, problem_count: 0,
}

export default function ExamPaperCreatePage() {
  const navigate = useNavigate()

  const [courseId,          setCourseId]          = useState('')
  const [title,             setTitle]             = useState('')
  const [examType,          setExamType]          = useState<ExamType>('END_SEM')
  const [totalMarks,        setTotalMarks]        = useState(100)
  const [durationMins,      setDurationMins]      = useState(180)
  const [unitsRaw,          setUnitsRaw]          = useState('1,2,3')
  const [format,            setFormat]            = useState<QuestionFormatConfig>(DEFAULT_FORMAT)
  const [dist,              setDist]              = useState<BloomsDistribution>(DEFAULT_DIST)
  const [specialInstructions, setSpecialInstructions] = useState('')
  const [error,             setError]             = useState<string | null>(null)

  const bloomSum = Object.values(dist).reduce((a, b) => a + b, 0)

  const { mutate, isPending } = useMutation({
    mutationFn: (payload: ExamPaperCreatePayload) => createExamPaper(payload),
    onSuccess: (res) => {
      navigate(`/exams/${res.paper_id}`)
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message
      setError(msg ?? 'Failed to create exam paper.')
    },
  })

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)

    if (Math.abs(bloomSum - 100) > 1) {
      setError(`Bloom's distribution must sum to 100 (current: ${bloomSum.toFixed(1)}).`)
      return
    }
    if (!courseId.trim()) {
      setError('Course ID is required.')
      return
    }

    const units = unitsRaw
      .split(',')
      .map(s => parseInt(s.trim(), 10))
      .filter(n => !isNaN(n) && n > 0)

    if (units.length === 0) {
      setError('At least one unit must be specified.')
      return
    }

    const totalQuestions =
      format.mcq_count + format.short_count + format.long_count + format.problem_count
    if (totalQuestions === 0) {
      setError('At least one question format must have count > 0.')
      return
    }

    mutate({
      course_id:             courseId.trim(),
      title:                 title.trim(),
      exam_type:             examType,
      total_marks:           totalMarks,
      duration_mins:         durationMins,
      units_included:        units,
      question_format:       format,
      requested_dist:        dist,
      special_instructions:  specialInstructions || undefined,
    })
  }

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={() => navigate('/exams')}>
          <ChevronLeft className="w-5 h-5" />
        </Button>
        <div className="flex items-center gap-2">
          <FileText className="w-6 h-6 text-indigo-600" />
          <h1 className="text-2xl font-bold text-gray-900">New Exam Paper</h1>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6 bg-white rounded-2xl border border-gray-200 p-6">

        {/* Basic info */}
        <section className="space-y-4">
          <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide">Paper Details</h2>

          <div className="space-y-2">
            <label className="text-sm font-medium text-gray-700">Title *</label>
            <input
              required
              value={title}
              onChange={e => setTitle(e.target.value)}
              placeholder="e.g. End Semester Exam – Nov 2026"
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <label className="text-sm font-medium text-gray-700">Course ID *</label>
              <input
                required
                value={courseId}
                onChange={e => setCourseId(e.target.value)}
                placeholder="UUID of course"
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-300"
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium text-gray-700">Exam Type</label>
              <select
                value={examType}
                onChange={e => setExamType(e.target.value as ExamType)}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
              >
                {EXAM_TYPES.map(t => (
                  <option key={t} value={t}>{t.replace('_', ' ')}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-4">
            <div className="space-y-2">
              <label className="text-sm font-medium text-gray-700">Total Marks *</label>
              <input
                type="number" min={1} max={500} required
                value={totalMarks}
                onChange={e => setTotalMarks(Number(e.target.value))}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium text-gray-700">Duration (min) *</label>
              <input
                type="number" min={15} max={600} required
                value={durationMins}
                onChange={e => setDurationMins(Number(e.target.value))}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium text-gray-700">Units (comma-separated)</label>
              <input
                value={unitsRaw}
                onChange={e => setUnitsRaw(e.target.value)}
                placeholder="1,2,3"
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
              />
            </div>
          </div>
        </section>

        {/* Question format */}
        <section className="space-y-4">
          <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide">Question Format</h2>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            {(
              [
                { key: 'mcq_count',     label: 'MCQ' },
                { key: 'short_count',   label: 'Short Answer' },
                { key: 'long_count',    label: 'Long Answer' },
                { key: 'problem_count', label: 'Problem Solving' },
              ] as const
            ).map(({ key, label }) => (
              <div key={key} className="space-y-1">
                <label className="text-xs font-medium text-gray-600">{label}</label>
                <input
                  type="number" min={0} max={50}
                  value={format[key]}
                  onChange={e => setFormat(prev => ({ ...prev, [key]: Number(e.target.value) }))}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                />
              </div>
            ))}
          </div>
        </section>

        {/* Bloom's distribution */}
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide">Bloom's Distribution (%)</h2>
            <span className={`text-sm font-semibold ${Math.abs(bloomSum - 100) > 1 ? 'text-red-600' : 'text-green-600'}`}>
              Total: {bloomSum.toFixed(0)}%
            </span>
          </div>

          {/* Distribution bar */}
          <div className="flex h-3 rounded-full overflow-hidden gap-0.5">
            {BLOOM_LEVELS.map(({ key, color }) => (
              <div
                key={key}
                className={`${color} transition-all`}
                style={{ width: `${dist[key]}%` }}
              />
            ))}
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {BLOOM_LEVELS.map(({ key, label, color }) => (
              <div key={key} className="space-y-1">
                <label className="flex items-center gap-1.5 text-xs font-medium text-gray-600">
                  <span className={`w-2 h-2 rounded-full ${color}`} />
                  {label}
                </label>
                <div className="flex items-center gap-1">
                  <input
                    type="number" min={0} max={100} step={5}
                    value={dist[key]}
                    onChange={e => setDist(prev => ({ ...prev, [key]: Number(e.target.value) }))}
                    className="w-full border border-gray-200 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                  />
                  <span className="text-xs text-gray-400">%</span>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Special instructions */}
        <section className="space-y-2">
          <label className="text-sm font-medium text-gray-700">Special Instructions (optional)</label>
          <textarea
            rows={3}
            value={specialInstructions}
            onChange={e => setSpecialInstructions(e.target.value)}
            placeholder="e.g. Focus on practical application questions, avoid theoretical definitions."
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 resize-none"
          />
        </section>

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-600">
            {error}
          </div>
        )}

        <div className="flex justify-end gap-3">
          <Button variant="outline" type="button" onClick={() => navigate('/exams')}>
            Cancel
          </Button>
          <Button
            type="submit"
            disabled={isPending}
            className="bg-indigo-600 hover:bg-indigo-700 text-white gap-2"
          >
            {isPending ? (
              <><Loader2 className="w-4 h-4 animate-spin" /> Generating…</>
            ) : (
              'Generate Paper'
            )}
          </Button>
        </div>
      </form>
    </div>
  )
}
