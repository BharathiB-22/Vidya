// M08 Exam Setter — Faculty: create an exam paper.
//
// The faculty's whole mental model, and nothing else:
//
//     1. Create Sections          2. Define section rules
//     3. Add question definitions 4. Choose marks
//     5. Choose unit coverage     6. Compulsory / any / OR
//     7. Bloom's  8. Difficulty   9. CO mapping
//
// There is no template "type" to choose, and no university is named or implied
// anywhere in this file. Any pattern — "answer any 5 of 8", "Q1 a) b) c)", "one
// full question per module" — is expressed as sections, rules and definitions.
//
// Units come from the course's APPROVED syllabus and nowhere else. If the course
// has no approved syllabus, paper creation is blocked rather than falling back to
// invented unit numbers: a paper over units that do not exist is not a paper.
import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { AlertTriangle, ChevronLeft, Eye, FileText, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { createExamPaper } from '@/lib/api/exam'
import { listAllCourses } from '@/lib/api/programs'
import { listSyllabuses, getSyllabus } from '@/lib/api/syllabuses'
import { assignmentsApi } from '@/lib/api/assignments'
import { useWorkspace } from '@/lib/workspace'
import { getErrorMessage } from '@/lib/api'
import PaperStructureBuilder from '@/components/exam/PaperStructureBuilder'
import PaperPreview from '@/components/exam/PaperPreview'
import {
  TEMPLATE_VERSION,
  compileSpecs,
  newSection,
  templateTotals,
  type PaperSection,
} from '@/lib/paperTemplate'
import type {
  BloomsDistribution,
  ExamPaperCreatePayload,
  ExamType,
  ExamWorkflow,
} from '@/types/exam'

const BLOOM_BARS: Array<{ key: keyof BloomsDistribution; label: string; color: string }> = [
  { key: 'remember',   label: 'Remember',   color: 'bg-red-400' },
  { key: 'understand', label: 'Understand', color: 'bg-orange-400' },
  { key: 'apply',      label: 'Apply',      color: 'bg-yellow-400' },
  { key: 'analyse',    label: 'Analyse',    color: 'bg-green-400' },
  { key: 'evaluate',   label: 'Evaluate',   color: 'bg-blue-400' },
  { key: 'create',     label: 'Create',     color: 'bg-purple-400' },
]

// Institutional assessment / exam names, chosen per workflow. Display labels
// only — they map to the paper title (+ a derived exam_type enum) and change no
// workflow logic. "Custom" reveals a free-text field.
const INTERNAL_ASSESSMENT_NAMES = [
  'IA 1', 'IA 2', 'IA 3', 'MSE 1', 'MSE 2', 'MSE 3', 'CIE 1', 'CIE 2', 'Assignment', 'Custom',
]

const BOARD_EXAM_NAMES = [
  'Mid Semester', 'End Semester', 'Supplementary', 'Improvement', 'Custom',
]

// Map the selected name to the backend exam_type enum (kept valid: one of
// MID_SEM / END_SEM / QUIZ / INTERNAL / CUSTOM). The friendly name lives in title.
function deriveExamType(workflow: ExamWorkflow, name: string): ExamType {
  if (workflow === 'INTERNAL') return /^mse/i.test(name) ? 'MID_SEM' : 'INTERNAL'
  switch (name) {
    case 'Mid Semester': return 'MID_SEM'
    case 'End Semester':
    case 'Supplementary':
    case 'Improvement':  return 'END_SEM'
    default:             return 'CUSTOM'
  }
}

const DEFAULT_DIST: BloomsDistribution = {
  remember: 20, understand: 20, apply: 20, analyse: 20, evaluate: 10, create: 10,
}

// One shape for a pickable course across both sources (faculty assignments and
// the programme catalog). `program_title` is read off the course, never chosen.
interface SelectableCourse {
  id:            string
  code:          string
  title:         string
  semester:      number | null
  program_title: string | null
}

export default function ExamPaperCreatePage() {
  const navigate = useNavigate()
  const { activeWorkspace } = useWorkspace()
  // Faculty may only set papers for subjects assigned to them: their course
  // dropdown comes from their own assignments, never the full programme catalog.
  // Board/Admin (who own semester papers) pick from the whole catalog.
  const isFacultyMode = activeWorkspace === 'FACULTY'

  // A paper is identified by its Course, and nothing else. The course already
  // belongs to a semester, which belongs to a program — so the program is read
  // off the selected course and is never chosen by hand.
  const [courseId,          setCourseId]          = useState('')
  const [examWorkflow,      setExamWorkflow]      = useState<ExamWorkflow>('BOARD_EXAM')
  const [examName,          setExamName]          = useState('End Semester')
  const [customName,        setCustomName]        = useState('')
  const [durationMins,      setDurationMins]      = useState(180)
  const [sections,          setSections]          = useState<PaperSection[]>([])
  const [dist,              setDist]              = useState<BloomsDistribution>(DEFAULT_DIST)
  const [specialInstructions, setSpecialInstructions] = useState('')
  const [selectedUnits,     setSelectedUnits]     = useState<number[]>([])
  const [mode,              setMode]              = useState<'AI' | 'MANUAL'>('AI')
  const [error,             setError]             = useState<string | null>(null)

  const bloomSum = Object.values(dist).reduce((a, b) => a + b, 0)
  const isInternal = examWorkflow === 'INTERNAL'
  const nameOptions = isInternal ? INTERNAL_ASSESSMENT_NAMES : BOARD_EXAM_NAMES
  const isCustomName = examName === 'Custom'
  const effectiveTitle = isCustomName ? customName.trim() : examName
  const derivedExamType = deriveExamType(examWorkflow, examName)

  // The approved catalog: Board/Admin choose a course from it directly, and both
  // modes use it to resolve the program a chosen course belongs to.
  const { data: allCourses = [], isLoading: coursesLoading } = useQuery({
    queryKey: ['all-courses', 'approved'],
    queryFn: () => listAllCourses({ program_status: 'APPROVED' }),
    staleTime: 60_000,
  })

  // Faculty: assigned subjects only (self-scoped by the backend).
  const { data: myAssignments, isLoading: assignmentsLoading } = useQuery({
    queryKey: ['my-assignments'],
    queryFn: () => assignmentsApi.listMine(),
    enabled: isFacultyMode,
    staleTime: 5 * 60 * 1000,
  })

  const programByCourseId = useMemo(
    () => new Map(allCourses.map(c => [c.id, c.program_title])),
    [allCourses],
  )

  const facultyCourses = useMemo(() => {
    const seen = new Map<string, SelectableCourse>()
    for (const a of myAssignments?.items ?? []) {
      if (!a.is_active || !a.course || seen.has(a.course_id)) continue
      seen.set(a.course_id, {
        id: a.course_id,
        code: a.course.code,
        title: a.course.title,
        semester: a.semester?.number ?? null,
        program_title: programByCourseId.get(a.course_id) ?? null,
      })
    }
    return [...seen.values()]
  }, [myAssignments, programByCourseId])

  const catalogCourses: SelectableCourse[] = useMemo(
    () => allCourses.map(c => ({
      id: c.id, code: c.code, title: c.title, semester: c.semester, program_title: c.program_title,
    })),
    [allCourses],
  )

  const selectableCourses = isFacultyMode ? facultyCourses : catalogCourses
  const selectedCourse = selectableCourses.find(c => c.id === courseId)
  const coursesBusy = isFacultyMode ? assignmentsLoading : coursesLoading

  const coursesByProgram = useMemo(() => {
    const groups = new Map<string, SelectableCourse[]>()
    for (const c of catalogCourses) {
      const key = c.program_title ?? 'Other'
      groups.set(key, [...(groups.get(key) ?? []), c])
    }
    return [...groups.entries()].sort((a, b) => a[0].localeCompare(b[0]))
  }, [catalogCourses])

  // ── The syllabus gate ──────────────────────────────────────────────────────
  // Units, and the COs a question may map to, come from the course's official
  // (LOCKED/APPROVED) syllabus — the same source the generation worker reads. No
  // approved syllabus, no paper: there is nothing legitimate to set questions on.
  const { data: syllabusList, isLoading: syllabusLoading } = useQuery({
    queryKey: ['exam-course-syllabuses', courseId],
    queryFn:  () => listSyllabuses({ course_id: courseId }),
    enabled:  !!courseId,
    staleTime: 60_000,
  })
  const officialSyllabus = useMemo(() => {
    const items = (syllabusList?.items ?? []).filter(s => s.status === 'LOCKED' || s.status === 'APPROVED')
    return [...items].sort((a, b) => b.version - a.version)[0] ?? null
  }, [syllabusList])

  const { data: syllabusDetail, isLoading: detailLoading } = useQuery({
    queryKey: ['exam-syllabus-detail', officialSyllabus?.id],
    queryFn:  () => getSyllabus(officialSyllabus!.id),
    enabled:  !!officialSyllabus,
    staleTime: 60_000,
  })

  const syllabusBusy = !!courseId && (syllabusLoading || (!!officialSyllabus && detailLoading))
  // Whatever the syllabus says — six units, or two. The builder follows it.
  const syllabusUnits = syllabusDetail?.units ?? []
  const outcomes = useMemo(
    () => (syllabusDetail?.outcomes ?? []).map(o => ({ id: o.id, code: o.code })),
    [syllabusDetail],
  )
  const hasSyllabus = !!officialSyllabus && syllabusUnits.length > 0
  const syllabusBlocked = !!courseId && !syllabusBusy && !hasSyllabus

  const effectiveUnits = useMemo(
    () => [...selectedUnits].sort((a, b) => a - b),
    [selectedUnits],
  )
  const unitsKey = effectiveUnits.join(',')

  // A newly chosen course brings its own syllabus: default to covering all of it,
  // which is what a paper usually does, and is a starting point not a decision.
  useEffect(() => {
    setSelectedUnits(syllabusUnits.map(u => u.unit_number))
  }, [officialSyllabus?.id, syllabusUnits.length]) // eslint-disable-line react-hooks/exhaustive-deps

  function toggleUnit(n: number) {
    setSelectedUnits(prev => prev.includes(n) ? prev.filter(x => x !== n) : [...prev, n])
  }

  function handleCourseChange(id: string) {
    setCourseId(id)
    setSelectedUnits([])
    // A template is written against a syllabus. Carrying one to another course
    // would silently point definitions at units that course may not have.
    setSections([])
  }

  // The template document — the single source of truth for this paper's
  // structure. It is what gets stored, what the AI is told to reproduce, and what
  // the editor and the PDF rebuild the paper from.
  const templateDoc = useMemo(
    () => ({ version: TEMPLATE_VERSION, sections }),
    [sections],
  )

  const { printed: printedTotal, evaluation: evaluationTotal } = templateTotals(templateDoc)
  const specs = useMemo(
    () => compileSpecs(templateDoc, effectiveUnits),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [templateDoc, unitsKey],
  )

  // The paper seen from the syllabus-coverage angle — what a Board member checks.
  const unitCoverage = useMemo(() => {
    const byUnit = new Map<number, number>()
    for (const s of specs) {
      for (const u of s.unit_numbers) byUnit.set(u, (byUnit.get(u) ?? 0) + 1)
    }
    return [...byUnit.entries()].sort((a, b) => a[0] - b[0])
  }, [specs])

  const uncoveredUnits = effectiveUnits.filter(u => !unitCoverage.some(([n]) => n === u))

  const { mutate, isPending } = useMutation({
    mutationFn: (payload: ExamPaperCreatePayload) => createExamPaper(payload),
    onSuccess: (res) => navigate(`/exams/${res.paper_id}`),
    onError: (err: unknown) => setError(getErrorMessage(err)),
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
    if (!hasSyllabus) {
      setError('This course has no approved syllabus, so its units are unknown. '
             + 'A paper cannot be set until the syllabus is approved.')
      return
    }
    if (!effectiveTitle) {
      setError(isInternal ? 'Please choose or enter an Assessment Name.' : 'Please choose or enter an Exam Name.')
      return
    }
    if (effectiveUnits.length === 0) {
      setError('Select at least one unit for the paper to cover.')
      return
    }
    if (specs.length === 0) {
      setError('Add at least one section with a question definition.')
      return
    }
    if (evaluationTotal <= 0) {
      setError('The paper has no evaluated marks — check the section rules and marks.')
      return
    }
    if (evaluationTotal > 500) {
      setError(`Evaluation total is ${evaluationTotal} marks — the maximum is 500. Reduce the counts or marks.`)
      return
    }

    // The template IS the paper's structure. It is stored verbatim, and the
    // worker, the editor and the PDF all rebuild the paper from it — so no
    // blueprint is sent alongside it to drift out of step.
    mutate({
      course_id:             courseId.trim(),
      title:                 effectiveTitle,
      creation_mode:         mode,
      exam_type:             derivedExamType,
      exam_workflow:         examWorkflow,
      total_marks:           evaluationTotal,
      duration_mins:         durationMins,
      units_included:        effectiveUnits,
      template_definition:   templateDoc,
      requested_dist:        dist,
      special_instructions:  specialInstructions || undefined,
    })
  }

  const courseLabel = selectedCourse ? `${selectedCourse.code} — ${selectedCourse.title}` : null

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={() => navigate('/exams')}>
          <ChevronLeft className="w-5 h-5" />
        </Button>
        <div className="flex items-center gap-2">
          <FileText className="w-6 h-6 text-indigo-600" />
          <h1 className="text-2xl font-bold text-gray-900">New Exam Paper</h1>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,26rem)] gap-6 items-start">
        <form onSubmit={handleSubmit} className="space-y-6 bg-white rounded-2xl border border-gray-200 p-6">

          {/* Creation mode — AI assists, faculty always has full control */}
          <section className="space-y-3">
            <h2 className="text-sm font-semibold text-foreground uppercase tracking-wide">Creation Mode</h2>
            <div className="grid grid-cols-2 gap-3">
              {([
                { value: 'AI' as const, title: 'Generate with AI', desc: 'AI drafts questions from the syllabus; you edit freely afterwards.' },
                { value: 'MANUAL' as const, title: 'Create Manually', desc: 'Start with an empty paper and add every question by hand.' },
              ]).map(opt => (
                <label
                  key={opt.value}
                  className={`flex items-start gap-3 px-4 py-3 rounded-xl border-2 cursor-pointer transition-colors ${
                    mode === opt.value ? 'border-indigo-500 bg-indigo-50' : 'border-gray-200 bg-white hover:border-gray-300'
                  }`}
                >
                  <input type="radio" name="creation_mode" value={opt.value} checked={mode === opt.value}
                    onChange={() => setMode(opt.value)} className="mt-0.5 accent-indigo-600" />
                  <div>
                    <p className="text-sm font-semibold text-gray-800">{opt.title}</p>
                    <p className="text-xs text-gray-500 mt-0.5">{opt.desc}</p>
                  </div>
                </label>
              ))}
            </div>
          </section>

          {/* Exam Workflow */}
          <section className="space-y-3">
            <h2 className="text-sm font-semibold text-foreground uppercase tracking-wide">Exam Workflow</h2>
            <div className="grid grid-cols-2 gap-3">
              {([
                {
                  value: 'BOARD_EXAM' as ExamWorkflow,
                  title: 'Board Exam',
                  desc:  '3-gate: Faculty → Scrutinizer → Board decision → Seal & Release',
                },
                {
                  value: 'INTERNAL' as ExamWorkflow,
                  title: 'Internal Assessment',
                  desc:  'Faculty → Dean review → Approve. No Board committee involved.',
                },
              ]).map(opt => (
                <label
                  key={opt.value}
                  className={`flex items-start gap-3 px-4 py-3 rounded-xl border-2 cursor-pointer transition-colors ${
                    examWorkflow === opt.value ? 'border-indigo-500 bg-indigo-50' : 'border-gray-200 bg-white hover:border-gray-300'
                  }`}
                >
                  <input
                    type="radio" name="exam_workflow" value={opt.value}
                    checked={examWorkflow === opt.value}
                    onChange={() => {
                      setExamWorkflow(opt.value)
                      setExamName(opt.value === 'INTERNAL' ? 'IA 1' : 'End Semester')
                      setCustomName('')
                    }}
                    className="mt-0.5 accent-indigo-600"
                  />
                  <div>
                    <p className="text-sm font-semibold text-gray-800">{opt.title}</p>
                    <p className="text-xs text-gray-500 mt-0.5">{opt.desc}</p>
                  </div>
                </label>
              ))}
            </div>
          </section>

          {/* Basic info */}
          <section className="space-y-4">
            <h2 className="text-sm font-semibold text-foreground uppercase tracking-wide">Paper Details</h2>

            <div className="space-y-2">
              <label className="text-sm font-medium text-gray-700">
                {isInternal ? 'Assessment Name *' : 'Exam Name *'}
              </label>
              <select
                value={examName}
                onChange={e => setExamName(e.target.value)}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 bg-white"
              >
                {nameOptions.map(n => <option key={n} value={n}>{n}</option>)}
              </select>
              {isCustomName && (
                <input
                  value={customName}
                  onChange={e => setCustomName(e.target.value)}
                  placeholder={isInternal ? 'Custom assessment name (e.g. Surprise Test 1)' : 'Custom exam name (e.g. Re-Exam Jan 2027)'}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                />
              )}
              <p className="text-xs text-gray-600">
                Display name only — it identifies the paper and maps to the “{derivedExamType.replace('_', ' ')}” exam type.
              </p>
            </div>

            {/* Course selection — the paper's only identity input. */}
            <div className="rounded-lg border border-gray-100 bg-gray-50 px-4 py-4 space-y-3">
              <p className="text-xs font-semibold text-foreground uppercase tracking-wide">Course Selection</p>

              <div className="space-y-1">
                <label className="text-sm font-medium text-gray-700">Course *</label>
                {coursesBusy ? (
                  <div className="flex items-center gap-2 py-2 text-sm text-gray-600">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    {isFacultyMode ? 'Loading your subjects…' : 'Loading courses…'}
                  </div>
                ) : selectableCourses.length === 0 ? (
                  <p className="text-sm text-amber-700 bg-amber-50 rounded-lg px-3 py-2">
                    {isFacultyMode
                      ? 'You have no assigned subjects. Papers can only be set for subjects assigned to you.'
                      : 'No courses found in any approved program. Please approve a program first.'}
                  </p>
                ) : isFacultyMode ? (
                  <select
                    value={courseId}
                    onChange={e => handleCourseChange(e.target.value)}
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 bg-white"
                  >
                    <option value="">— Select an assigned subject —</option>
                    {facultyCourses.map(c => (
                      <option key={c.id} value={c.id}>
                        {c.code} — {c.title}{c.semester != null ? ` (Sem ${c.semester})` : ''}
                      </option>
                    ))}
                  </select>
                ) : (
                  <select
                    value={courseId}
                    onChange={e => handleCourseChange(e.target.value)}
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 bg-white"
                  >
                    <option value="">— Select a course —</option>
                    {coursesByProgram.map(([programTitle, courses]) => (
                      <optgroup key={programTitle} label={programTitle}>
                        {courses.map(c => (
                          <option key={c.id} value={c.id}>
                            {c.code} — {c.title} (Sem {c.semester})
                          </option>
                        ))}
                      </optgroup>
                    ))}
                  </select>
                )}
                <p className="text-xs text-gray-600">
                  {isFacultyMode
                    ? 'Only subjects assigned to you appear here.'
                    : 'Grouped by program. Selecting a course sets its semester and program.'}
                </p>
              </div>

              {/* Derived, never chosen. */}
              {selectedCourse && (
                <dl className="grid grid-cols-2 gap-x-4 gap-y-1 rounded-lg border border-gray-200 bg-white px-3 py-2.5 text-sm">
                  <div className="flex gap-2">
                    <dt className="text-gray-500">Program</dt>
                    <dd className="text-gray-800 font-medium break-words">{selectedCourse.program_title ?? '—'}</dd>
                  </div>
                  <div className="flex gap-2">
                    <dt className="text-gray-500">Semester</dt>
                    <dd className="text-gray-800 font-medium">
                      {selectedCourse.semester != null ? `Semester ${selectedCourse.semester}` : '—'}
                    </dd>
                  </div>
                </dl>
              )}
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <label className="text-sm font-medium text-gray-700">Marks (from the template)</label>
                <div className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-gray-50 text-gray-700">
                  <span className="font-semibold">Max {evaluationTotal}</span>
                  <span className="text-gray-600"> · Printed {printedTotal}</span>
                </div>
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
            </div>
          </section>

          {/* Units — the approved syllabus's own units, and nothing else. */}
          <section className="space-y-2">
            <h2 className="text-sm font-semibold text-foreground uppercase tracking-wide">Syllabus Coverage</h2>
            {!courseId ? (
              <p className="text-sm text-gray-600 bg-gray-50 rounded-lg px-3 py-2">
                Select a course to load its approved syllabus units.
              </p>
            ) : syllabusBusy ? (
              <div className="flex items-center gap-2 py-2 text-sm text-gray-600">
                <Loader2 className="h-4 w-4 animate-spin" /> Loading the approved syllabus…
              </div>
            ) : syllabusBlocked ? (
              <div className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
                <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
                <div className="space-y-1">
                  <p className="text-sm font-semibold text-amber-900">
                    No approved syllabus for this course
                  </p>
                  <p className="text-xs text-amber-800">
                    A paper's units come from the approved syllabus. Until one exists,
                    there are no units to set questions on — so paper creation is
                    blocked rather than inventing them.
                  </p>
                </div>
              </div>
            ) : (
              <>
                <p className="text-xs text-gray-500">
                  From <span className="font-medium">{officialSyllabus?.status === 'LOCKED' ? 'the locked' : 'the approved'}</span>{' '}
                  syllabus v{officialSyllabus?.version}. Tick the units this paper covers.
                </p>
                <div className="rounded-lg border border-gray-200 divide-y divide-gray-100 overflow-hidden">
                  {syllabusUnits.map(u => (
                    <label key={u.unit_number} className="flex items-center gap-3 px-3 py-2 cursor-pointer hover:bg-gray-50 transition-colors">
                      <input
                        type="checkbox"
                        checked={selectedUnits.includes(u.unit_number)}
                        onChange={() => toggleUnit(u.unit_number)}
                        className="accent-indigo-600 w-4 h-4"
                      />
                      <span className="text-sm text-gray-700">
                        <span className="font-medium">Unit {u.unit_number}</span>
                        {u.title ? ` — ${u.title}` : ''}
                      </span>
                    </label>
                  ))}
                </div>
              </>
            )}
          </section>

          {/* Structure — sections and question definitions. The whole builder. */}
          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-foreground uppercase tracking-wide">Paper Structure</h2>
              {sections.length > 0 && (
                <span className="text-xs text-gray-500">
                  {specs.length} question{specs.length === 1 ? '' : 's'} · {sections.length} section{sections.length === 1 ? '' : 's'}
                </span>
              )}
            </div>
            <p className="text-xs text-gray-600">
              Say how many questions, worth what, over which units. The compiler
              distributes them across the units you pick — you never place a
              question on a unit by hand.
            </p>

            {!hasSyllabus ? (
              <p className="text-sm text-gray-600 bg-gray-50 border border-dashed border-gray-200 rounded-xl px-4 py-6 text-center">
                The structure builder unlocks once the course has an approved syllabus.
              </p>
            ) : (
              <PaperStructureBuilder
                sections={sections}
                onChange={setSections}
                units={syllabusUnits
                  .filter(u => effectiveUnits.includes(u.unit_number))
                  .map(u => ({ unit_number: u.unit_number, title: u.title ?? null }))}
                outcomes={outcomes}
              />
            )}

            {sections.length === 0 && hasSyllabus && (
              <Button
                type="button" variant="ghost" size="sm" className="text-indigo-600"
                onClick={() => setSections([newSection(0)])}
              >
                Start with a section
              </Button>
            )}

            {uncoveredUnits.length > 0 && (
              <p className="text-xs text-amber-600">
                No question covers unit{uncoveredUnits.length === 1 ? '' : 's'}{' '}
                {uncoveredUnits.join(', ')} — either add a definition for {uncoveredUnits.length === 1 ? 'it' : 'them'} or
                untick {uncoveredUnits.length === 1 ? 'it' : 'them'} above.
              </p>
            )}
          </section>

          {/* Bloom's distribution */}
          <section className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-foreground uppercase tracking-wide">Bloom's Distribution (%)</h2>
              <span className={`text-sm font-semibold ${Math.abs(bloomSum - 100) > 1 ? 'text-red-600' : 'text-green-600'}`}>
                Total: {bloomSum.toFixed(0)}%
              </span>
            </div>
            <p className="text-xs text-gray-600">
              The paper's overall mix. A question definition may override it for its
              own questions.
            </p>

            <div className="flex h-3 rounded-full overflow-hidden gap-0.5">
              {BLOOM_BARS.map(({ key, color }) => (
                <div key={key} className={`${color} transition-all`} style={{ width: `${dist[key]}%` }} />
              ))}
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {BLOOM_BARS.map(({ key, label, color }) => (
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
                    <span className="text-xs text-gray-600">%</span>
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

          {/* Review — a read-only summary of what will be generated. */}
          <section className="rounded-xl border border-indigo-100 bg-indigo-50/40 p-4 space-y-3">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-indigo-800 uppercase tracking-wide">
              <Eye className="w-4 h-4" /> Review before generating
            </h2>
            <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1.5 text-sm">
              <ReviewRow label="Course"   value={courseLabel ?? '—'} />
              <ReviewRow label="Semester" value={selectedCourse?.semester != null ? `Semester ${selectedCourse.semester}` : '—'} />
              <ReviewRow label="Program"  value={selectedCourse?.program_title ?? '—'} derived />
              <ReviewRow label={isInternal ? 'Assessment Name' : 'Exam Name'} value={effectiveTitle || '—'} />
              <ReviewRow label="Exam Type" value={derivedExamType.replace('_', ' ')} derived />
              <ReviewRow label="Workflow" value={isInternal ? 'Internal Assessment' : 'Board Exam'} />
              <ReviewRow label="Duration" value={`${durationMins} min`} />
              <ReviewRow label="Printed Marks" value={`${printedTotal}`} derived />
              <ReviewRow label="Evaluation (Max) Marks" value={`${evaluationTotal}`} derived />
              <ReviewRow label="Units Covered" value={effectiveUnits.length ? effectiveUnits.join(', ') : '—'} />
              <ReviewRow
                label="Unit Distribution" derived
                value={unitCoverage.length ? unitCoverage.map(([u, n]) => `U${u}: ${n}q`).join('   ·   ') : '—'}
              />
              <ReviewRow label="Bloom's Distribution" value={BLOOM_BARS.map(b => `${b.label} ${dist[b.key]}%`).join(' · ')} />
            </dl>
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
              disabled={isPending || syllabusBlocked}
              className="bg-indigo-600 hover:bg-indigo-700 text-white gap-2"
            >
              {isPending ? (
                <><Loader2 className="w-4 h-4 animate-spin" /> {mode === 'MANUAL' ? 'Creating…' : 'Generating…'}</>
              ) : (
                mode === 'MANUAL' ? 'Create Manually' : 'Generate Paper'
              )}
            </Button>
          </div>
        </form>

        {/* Live preview — the same reconstruction the PDF prints. */}
        <div className="lg:sticky lg:top-6">
          <PaperPreview
            sections={sections}
            units={effectiveUnits}
            title={effectiveTitle}
            courseLabel={courseLabel}
            durationMins={durationMins}
          />
        </div>
      </div>
    </div>
  )
}

function ReviewRow({ label, value, derived }: { label: string; value: string; derived?: boolean }) {
  return (
    <div className="flex gap-2">
      <dt className="text-gray-500 shrink-0">{label}</dt>
      <dd className="text-gray-800 font-medium break-words">
        {value}
        {derived && <span className="ml-1 text-[10px] uppercase tracking-wide text-gray-600">derived</span>}
      </dd>
    </div>
  )
}
