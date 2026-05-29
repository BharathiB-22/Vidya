// M08 Exam Setter — Faculty: create exam paper configuration form
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { FileText, Info, Loader2, ChevronLeft, AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { createExamPaper } from '@/lib/api/exam'
import { listPrograms, listCourses } from '@/lib/api/programs'
import { getErrorMessage } from '@/lib/api'
import type {
  BloomsDistribution,
  ExamPaperCreatePayload,
  ExamType,
  ExamWorkflow,
  QuestionFormatConfig,
  SectionConfig,
} from '@/types/exam'

const BLOOM_LEVELS: Array<{ key: keyof BloomsDistribution; label: string; color: string }> = [
  { key: 'remember',   label: 'Remember',   color: 'bg-red-400' },
  { key: 'understand', label: 'Understand', color: 'bg-orange-400' },
  { key: 'apply',      label: 'Apply',      color: 'bg-yellow-400' },
  { key: 'analyse',    label: 'Analyse',    color: 'bg-green-400' },
  { key: 'evaluate',   label: 'Evaluate',   color: 'bg-blue-400' },
  { key: 'create',     label: 'Create',     color: 'bg-purple-400' },
]

const EXAM_TYPES: ExamType[] = ['END_SEM', 'MID_SEM', 'QUIZ', 'INTERNAL', 'CUSTOM']

const SECTION_MARKS_OPTIONS = [1, 2, 3, 5, 8, 10, 15, 20]

const DEFAULT_DIST: BloomsDistribution = {
  remember: 20, understand: 20, apply: 20, analyse: 20, evaluate: 10, create: 10,
}

const DEFAULT_FORMAT: QuestionFormatConfig = {
  mcq_count: 5, short_count: 3, long_count: 2, problem_count: 0,
}

type SectionRow = Omit<SectionConfig, 'order' | 'instruction'>

const DEFAULT_SECTIONS: SectionRow[] = [
  { label: 'A', total_q: 10, answer_q: 10, marks_each: 2,  mcq_only: false },
  { label: 'B', total_q:  5, answer_q:  3, marks_each: 5,  mcq_only: false },
  { label: 'C', total_q:  3, answer_q:  2, marks_each: 10, mcq_only: false },
]

export default function ExamPaperCreatePage() {
  const navigate = useNavigate()

  const [programId,         setProgramId]         = useState('')
  const [semesterFilter,    setSemesterFilter]     = useState<number | ''>('')
  const [courseId,          setCourseId]          = useState('')
  const [title,             setTitle]             = useState('')
  const [examType,          setExamType]          = useState<ExamType>('END_SEM')
  const [examWorkflow,      setExamWorkflow]      = useState<ExamWorkflow>('BOARD_EXAM')
  const [totalMarks,        setTotalMarks]        = useState(100)
  const [durationMins,      setDurationMins]      = useState(180)
  const [unitsRaw,          setUnitsRaw]          = useState('1,2,3')
  const [format,            setFormat]            = useState<QuestionFormatConfig>(DEFAULT_FORMAT)
  const [dist,              setDist]              = useState<BloomsDistribution>(DEFAULT_DIST)
  const [specialInstructions, setSpecialInstructions] = useState('')
  const [useSectionLayout,  setUseSectionLayout]  = useState(false)
  const [sections,          setSections]          = useState<SectionRow[]>(DEFAULT_SECTIONS)
  const [error,             setError]             = useState<string | null>(null)

  const bloomSum = Object.values(dist).reduce((a, b) => a + b, 0)

  const isBoardMcqOnly =
    examWorkflow === 'BOARD_EXAM' &&
    format.mcq_count > 0 &&
    format.short_count === 0 &&
    format.long_count === 0 &&
    format.problem_count === 0

  const { data: programsData, isLoading: programsLoading } = useQuery({
    queryKey: ['programs', 'approved'],
    queryFn: () => listPrograms({ status: 'APPROVED', page_size: 200 }),
    staleTime: 60_000,
  })
  const programs = programsData?.items ?? []

  const { data: allCourses = [], isLoading: coursesLoading } = useQuery({
    queryKey: ['program-courses', programId],
    queryFn: () => listCourses(programId),
    enabled: !!programId,
    staleTime: 60_000,
  })

  const semesters = [...new Set(allCourses.map(c => c.semester))].sort((a, b) => a - b)
  const visibleCourses = semesterFilter === ''
    ? allCourses
    : allCourses.filter(c => c.semester === semesterFilter)

  function handleProgramChange(pid: string) {
    setProgramId(pid)
    setSemesterFilter('')
    setCourseId('')
  }

  function handleSemesterChange(val: string) {
    setSemesterFilter(val === '' ? '' : Number(val))
    setCourseId('')
  }

  function updateSection(index: number, field: keyof SectionRow, value: number | boolean) {
    setSections(prev => prev.map((s, i) => i === index ? { ...s, [field]: value } : s))
  }

  const { mutate, isPending } = useMutation({
    mutationFn: (payload: ExamPaperCreatePayload) => createExamPaper(payload),
    onSuccess: (res) => {
      navigate(`/exams/${res.paper_id}`)
    },
    onError: (err: unknown) => {
      setError(getErrorMessage(err))
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
      setError('Please select a course from the dropdown.')
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

    if (isBoardMcqOnly) {
      setError(
        'Board Exam papers cannot be MCQ-only. ' +
        'Add at least one Short Answer, Long Answer, or Problem Solving question.'
      )
      return
    }

    if (useSectionLayout) {
      for (const sec of sections) {
        if (sec.answer_q > sec.total_q) {
          setError(
            `Part ${sec.label}: "Answer Q" (${sec.answer_q}) cannot exceed "Total Q" (${sec.total_q}).`
          )
          return
        }
      }
    }

    const sectionConfig: SectionConfig[] | undefined = useSectionLayout
      ? sections.map((s, i) => ({ ...s, order: i }))
      : undefined

    mutate({
      course_id:             courseId.trim(),
      title:                 title.trim(),
      exam_type:             examType,
      exam_workflow:         examWorkflow,
      total_marks:           totalMarks,
      duration_mins:         durationMins,
      units_included:        units,
      question_format:       format,
      requested_dist:        dist,
      section_config:        sectionConfig,
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

          {/* Course selection — Program → Semester → Course */}
          <div className="rounded-lg border border-gray-100 bg-gray-50 px-4 py-4 space-y-3">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Course Selection</p>

            {/* Program */}
            <div className="space-y-1">
              <label className="text-sm font-medium text-gray-700">Program *</label>
              {programsLoading ? (
                <div className="flex items-center gap-2 py-2 text-sm text-gray-400">
                  <Loader2 className="h-4 w-4 animate-spin" /> Loading programs…
                </div>
              ) : programs.length === 0 ? (
                <p className="text-sm text-amber-700 bg-amber-50 rounded-lg px-3 py-2">
                  No approved programs found. Please approve a program first.
                </p>
              ) : (
                <select
                  value={programId}
                  onChange={e => handleProgramChange(e.target.value)}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 bg-white"
                >
                  <option value="">— Select a program —</option>
                  {programs.map(p => (
                    <option key={p.id} value={p.id}>{p.title}</option>
                  ))}
                </select>
              )}
            </div>

            {/* Semester filter — only shown when program has multiple semesters */}
            {programId && !coursesLoading && semesters.length > 1 && (
              <div className="space-y-1">
                <label className="text-sm font-medium text-gray-700">Semester</label>
                <select
                  value={semesterFilter}
                  onChange={e => handleSemesterChange(e.target.value)}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 bg-white"
                >
                  <option value="">All semesters</option>
                  {semesters.map(s => (
                    <option key={s} value={s}>Semester {s}</option>
                  ))}
                </select>
              </div>
            )}

            {/* Course */}
            {programId && (
              <div className="space-y-1">
                <label className="text-sm font-medium text-gray-700">Course *</label>
                {coursesLoading ? (
                  <div className="flex items-center gap-2 py-2 text-sm text-gray-400">
                    <Loader2 className="h-4 w-4 animate-spin" /> Loading courses…
                  </div>
                ) : visibleCourses.length === 0 ? (
                  <p className="text-sm text-amber-700 bg-amber-50 rounded-lg px-3 py-2">
                    No courses available for this program
                    {semesterFilter !== '' ? ` in Semester ${semesterFilter}` : ''}.
                  </p>
                ) : (
                  <select
                    value={courseId}
                    onChange={e => setCourseId(e.target.value)}
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 bg-white"
                  >
                    <option value="">— Select a course —</option>
                    {visibleCourses.map(c => (
                      <option key={c.id} value={c.id}>
                        {c.code} — {c.title}{semesters.length > 1 && semesterFilter === '' ? ` (Sem ${c.semester})` : ''}
                      </option>
                    ))}
                  </select>
                )}
              </div>
            )}
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

        {/* Exam Workflow */}
        <section className="space-y-3">
          <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide">Exam Workflow</h2>
          <div className="grid grid-cols-2 gap-3">
            {(
              [
                {
                  value: 'BOARD_EXAM' as ExamWorkflow,
                  title: 'Board Exam',
                  desc:  '3-gate: Faculty → Scrutinizer → Board decision → Seal & Release',
                },
                {
                  value: 'INTERNAL' as ExamWorkflow,
                  title: 'Internal Assessment',
                  desc:  'Faculty approves directly — no Board committee review required',
                },
              ]
            ).map(opt => (
              <label
                key={opt.value}
                className={`flex items-start gap-3 px-4 py-3 rounded-xl border-2 cursor-pointer transition-colors ${
                  examWorkflow === opt.value
                    ? 'border-indigo-500 bg-indigo-50'
                    : 'border-gray-200 bg-white hover:border-gray-300'
                }`}
              >
                <input
                  type="radio"
                  name="exam_workflow"
                  value={opt.value}
                  checked={examWorkflow === opt.value}
                  onChange={() => setExamWorkflow(opt.value)}
                  className="mt-0.5 accent-indigo-600"
                />
                <div>
                  <p className="text-sm font-semibold text-gray-800">{opt.title}</p>
                  <p className="text-xs text-gray-500 mt-0.5">{opt.desc}</p>
                </div>
              </label>
            ))}
          </div>

          {examWorkflow === 'INTERNAL' && (
            <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2.5 text-sm text-amber-800">
              <Info className="w-4 h-4 mt-0.5 shrink-0" />
              <span>
                Internal Assessment: after generation, Faculty approves the paper directly.
                It advances to <strong>Board Approved</strong> state without Board committee review.
              </span>
            </div>
          )}
        </section>

        {/* Section Layout */}
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide">Section Layout</h2>
            <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={useSectionLayout}
                onChange={e => setUseSectionLayout(e.target.checked)}
                className="rounded accent-indigo-600"
              />
              Use Part A / B / C structure
            </label>
          </div>

          {useSectionLayout && (
            <div className="rounded-xl border border-gray-200 overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    <th className="px-3 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Part</th>
                    <th className="px-3 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Total Q</th>
                    <th className="px-3 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Answer Q</th>
                    <th className="px-3 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Marks Each</th>
                    <th className="px-3 py-2.5 text-center text-xs font-semibold text-gray-500 uppercase tracking-wide">MCQ Only</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {sections.map((sec, i) => (
                    <tr key={sec.label} className="hover:bg-gray-50 transition-colors">
                      <td className="px-3 py-2.5">
                        <span className="inline-flex items-center justify-center w-7 h-7 rounded-lg bg-indigo-100 text-indigo-700 text-xs font-bold">
                          {sec.label}
                        </span>
                      </td>
                      <td className="px-3 py-2.5">
                        <input
                          type="number" min={1} max={30}
                          value={sec.total_q}
                          onChange={e => updateSection(i, 'total_q', Number(e.target.value))}
                          className="w-16 border border-gray-200 rounded-lg px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                        />
                      </td>
                      <td className="px-3 py-2.5">
                        <div>
                          <input
                            type="number" min={1} max={sec.total_q}
                            value={sec.answer_q}
                            onChange={e => updateSection(i, 'answer_q', Number(e.target.value))}
                            className={`w-16 border rounded-lg px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 ${
                              sec.answer_q > sec.total_q
                                ? 'border-red-400 bg-red-50'
                                : 'border-gray-200'
                            }`}
                          />
                          {sec.answer_q > sec.total_q && (
                            <p className="text-xs text-red-600 mt-0.5">max {sec.total_q}</p>
                          )}
                        </div>
                      </td>
                      <td className="px-3 py-2.5">
                        <select
                          value={sec.marks_each}
                          onChange={e => updateSection(i, 'marks_each', Number(e.target.value))}
                          className="border border-gray-200 rounded-lg px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 bg-white"
                        >
                          {SECTION_MARKS_OPTIONS.map(m => (
                            <option key={m} value={m}>{m}</option>
                          ))}
                        </select>
                      </td>
                      <td className="px-3 py-2.5 text-center">
                        <input
                          type="checkbox"
                          checked={sec.mcq_only}
                          onChange={e => updateSection(i, 'mcq_only', e.target.checked)}
                          className="accent-indigo-600 w-4 h-4"
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="px-4 py-2 bg-gray-50 border-t border-gray-100 text-xs text-gray-500 flex gap-4">
                <span>
                  Section marks total:{' '}
                  <strong className="text-gray-700">
                    {sections.reduce((sum, s) => sum + s.answer_q * s.marks_each, 0)}
                  </strong>
                </span>
                <span>
                  Questions set / answer:{' '}
                  <strong className="text-gray-700">
                    {sections.reduce((sum, s) => sum + s.total_q, 0)}
                  </strong>
                  {' / '}
                  <strong className="text-gray-700">
                    {sections.reduce((sum, s) => sum + s.answer_q, 0)}
                  </strong>
                </span>
              </div>
            </div>
          )}
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

          {isBoardMcqOnly && (
            <div className="flex items-start gap-2 bg-orange-50 border border-orange-200 rounded-lg px-3 py-2.5 text-sm text-orange-800">
              <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
              <span>
                <strong>Board Exam — MCQ-only not allowed.</strong>{' '}
                Board papers must include at least one Short Answer, Long Answer, or Problem Solving question.
              </span>
            </div>
          )}
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
            disabled={isPending || isBoardMcqOnly}
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
