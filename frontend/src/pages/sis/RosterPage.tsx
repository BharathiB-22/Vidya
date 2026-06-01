import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Users, UserPlus, MoveRight, UserMinus } from 'lucide-react'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { PageLoading } from '@/components/shared/PageLoading'
import { PageEmpty } from '@/components/shared/PageEmpty'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { addToast } from '@/hooks/useToast'
import { getErrorMessage } from '@/lib/api'
import { sisApi } from '@/lib/api/sis'
import { academicsApi } from '@/lib/api/academics'
import type { RosterStudent, StudentSummary } from '@/lib/api/sis'

// ---------------------------------------------------------------------------
// Enroll dialog — search + pick a student
// ---------------------------------------------------------------------------

function EnrollDialog({
  sectionId,
  open,
  onClose,
  onEnrolled,
}: {
  sectionId: string
  open: boolean
  onClose: () => void
  onEnrolled: () => void
}) {
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<StudentSummary | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const { data: students, isFetching } = useQuery({
    queryKey: ['sis-students', search],
    queryFn: () => sisApi.listStudents(search || undefined),
  })

  async function enroll() {
    if (!selected) return
    setBusy(true); setErr('')
    try {
      await sisApi.enrollStudent(selected.id, sectionId)
      addToast(`${selected.full_name} enrolled.`, 'success')
      onEnrolled(); onClose(); setSelected(null); setSearch('')
    } catch (e) { setErr(getErrorMessage(e)) }
    finally { setBusy(false) }
  }

  return (
    <Dialog open={open} onOpenChange={v => { if (!v) { onClose(); setSelected(null); setSearch('') } }}>
      <DialogContent className="max-w-lg">
        <DialogHeader><DialogTitle>Enroll a student</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <Input
            placeholder="Search by name or email…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            autoFocus
          />
          <div
            className="max-h-64 overflow-y-auto rounded-lg divide-y"
            style={{ border: '1px solid rgba(255,255,255,0.08)' }}
          >
            {isFetching ? (
              <p className="px-4 py-3 text-sm text-slate-500">Searching…</p>
            ) : (students ?? []).length === 0 ? (
              <p className="px-4 py-3 text-sm text-slate-500">No students found.</p>
            ) : (students ?? []).map(s => (
              <button
                key={s.id}
                onClick={() => setSelected(s)}
                className="w-full text-left px-4 py-2.5 flex items-center justify-between transition-colors"
                style={{
                  background: selected?.id === s.id ? 'rgba(16,185,129,0.08)' : 'transparent',
                  color: selected?.id === s.id ? '#34d399' : 'inherit',
                }}
              >
                <div>
                  <p className="text-sm font-medium text-slate-200">{s.full_name}</p>
                  <p className="text-xs text-slate-500">{s.email}{s.identifier ? ` · ${s.identifier}` : ''}</p>
                </div>
                {s.is_enrolled && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded font-bold"
                    style={{ background: 'rgba(251,191,36,0.1)', color: '#fbbf24', border: '1px solid rgba(251,191,36,0.2)' }}>
                    ENROLLED
                  </span>
                )}
              </button>
            ))}
          </div>
          {err && <p className="text-xs text-red-400">{err}</p>}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={enroll} disabled={!selected || selected.is_enrolled || busy}>
            {busy ? 'Enrolling…' : 'Enroll'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ---------------------------------------------------------------------------
// Move dialog — pick a different section in the same semester
// ---------------------------------------------------------------------------

function MoveDialog({
  enrollmentId,
  currentSectionId,
  semesterId,
  studentName,
  open,
  onClose,
  onMoved,
}: {
  enrollmentId: string
  currentSectionId: string
  semesterId: string
  studentName: string
  open: boolean
  onClose: () => void
  onMoved: () => void
}) {
  const [targetSectionId, setTargetSectionId] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const { data: sections } = useQuery({
    queryKey: ['acad-sections', semesterId],
    queryFn: () => academicsApi.listSections(semesterId),
    enabled: !!semesterId,
  })

  const otherSections = (sections ?? []).filter(s => s.id !== currentSectionId && s.is_active)

  async function move() {
    if (!targetSectionId) return
    setBusy(true); setErr('')
    try {
      await sisApi.moveStudent(enrollmentId, targetSectionId)
      addToast(`${studentName} moved.`, 'success')
      onMoved(); onClose(); setTargetSectionId('')
    } catch (e) { setErr(getErrorMessage(e)) }
    finally { setBusy(false) }
  }

  return (
    <Dialog open={open} onOpenChange={v => { if (!v) { onClose(); setTargetSectionId('') } }}>
      <DialogContent className="max-w-sm">
        <DialogHeader><DialogTitle>Move {studentName}</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <label className="block text-xs font-medium text-slate-400">Target section</label>
          <select
            value={targetSectionId}
            onChange={e => setTargetSectionId(e.target.value)}
            className="w-full px-3 py-2 text-sm rounded-lg bg-white/5 border border-white/10 text-slate-200"
          >
            <option value="">Select section…</option>
            {otherSections.map(s => (
              <option key={s.id} value={s.id}>Section {s.name}</option>
            ))}
          </select>
          {otherSections.length === 0 && (
            <p className="text-xs text-slate-500">No other active sections in this semester.</p>
          )}
          {err && <p className="text-xs text-red-400">{err}</p>}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={move} disabled={!targetSectionId || busy}>
            {busy ? 'Moving…' : 'Move'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

type LifecycleAction = 'unenroll' | 'move'

interface LifecycleState {
  action: LifecycleAction
  enrollment: RosterStudent
}

export default function RosterPage() {
  const navigate  = useNavigate()
  const qc        = useQueryClient()

  // Cascade selection state
  const [selSchool,   setSelSchool]   = useState('')
  const [selDept,     setSelDept]     = useState('')
  const [selProgram,  setSelProgram]  = useState('')
  const [selBatch,    setSelBatch]    = useState('')
  const [selSemester, setSelSemester] = useState('')
  const [selSection,  setSelSection]  = useState('')

  // Dialog state
  const [showEnroll,   setShowEnroll]   = useState(false)
  const [lifecycleState, setLifecycleState] = useState<LifecycleState | null>(null)

  // Cascade data queries
  const { data: schools }   = useQuery({ queryKey: ['sis-schools'],   queryFn: () => sisApi.listSchools() })
  const { data: allDepts }  = useQuery({ queryKey: ['acad-depts'],    queryFn: () => academicsApi.listDepartments() })
  const { data: programs }  = useQuery({
    queryKey: ['acad-programs', selDept],
    queryFn:  () => academicsApi.listPrograms(selDept),
    enabled:  !!selDept,
  })
  const { data: batches }   = useQuery({
    queryKey: ['acad-batches', selProgram],
    queryFn:  () => academicsApi.listBatches(selProgram),
    enabled:  !!selProgram,
  })
  const { data: semesters } = useQuery({
    queryKey: ['acad-semesters', selBatch],
    queryFn:  () => academicsApi.listSemesters(selBatch),
    enabled:  !!selBatch,
  })
  const { data: sections }  = useQuery({
    queryKey: ['acad-sections', selSemester],
    queryFn:  () => academicsApi.listSections(selSemester),
    enabled:  !!selSemester,
  })
  const { data: roster, isLoading: rosterLoading } = useQuery({
    queryKey: ['sis-roster', selSection],
    queryFn:  () => sisApi.getRoster(selSection),
    enabled:  !!selSection,
  })

  // Filter depts by selected school (client-side)
  const depts = selSchool
    ? (allDepts ?? []).filter(d => d.school_id === selSchool)
    : (allDepts ?? [])

  // Cascade clear helpers
  function pickSchool(id: string)   { setSelSchool(id);   setSelDept('');   setSelProgram(''); setSelBatch(''); setSelSemester(''); setSelSection('') }
  function pickDept(id: string)     { setSelDept(id);     setSelProgram(''); setSelBatch(''); setSelSemester(''); setSelSection('') }
  function pickProgram(id: string)  { setSelProgram(id);  setSelBatch(''); setSelSemester(''); setSelSection('') }
  function pickBatch(id: string)    { setSelBatch(id);    setSelSemester(''); setSelSection('') }
  function pickSemester(id: string) { setSelSemester(id); setSelSection('') }

  const unenrollMut = useMutation({
    mutationFn: (enrollmentId: string) => sisApi.unenrollStudent(enrollmentId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sis-roster', selSection] })
      addToast('Student unenrolled.', 'success')
      setLifecycleState(null)
    },
    onError: (e) => { addToast(getErrorMessage(e), 'error'); setLifecycleState(null) },
  })

  const selStyles = 'px-3 py-2 text-sm rounded-lg bg-white/5 border border-white/10 text-slate-200 disabled:opacity-40'

  const selectedSection = (sections ?? []).find(s => s.id === selSection)
  const selectedSemester = (semesters ?? []).find(s => s.id === selSemester)

  return (
    <PageShell>
      <PageHeader
        icon={Users}
        title="Enrollment Roster"
        subtitle="View and manage section-level student enrollment"
        action={
          selSection ? (
            <Button onClick={() => setShowEnroll(true)} className="flex items-center gap-1.5">
              <UserPlus className="h-4 w-4" /> Enroll student
            </Button>
          ) : undefined
        }
      />

      {/* ── Cascade filter bar ──────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2">
        <select value={selSchool} onChange={e => pickSchool(e.target.value)} className={selStyles}>
          <option value="">All schools</option>
          {(schools ?? []).map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>

        <select value={selDept} onChange={e => pickDept(e.target.value)} className={selStyles}>
          <option value="">Department…</option>
          {depts.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select>

        <select value={selProgram} onChange={e => pickProgram(e.target.value)} className={selStyles} disabled={!selDept}>
          <option value="">Program…</option>
          {(programs ?? []).map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>

        <select value={selBatch} onChange={e => pickBatch(e.target.value)} className={selStyles} disabled={!selProgram}>
          <option value="">Batch…</option>
          {(batches ?? []).map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
        </select>

        <select value={selSemester} onChange={e => pickSemester(e.target.value)} className={selStyles} disabled={!selBatch}>
          <option value="">Semester…</option>
          {(semesters ?? []).map(s => (
            <option key={s.id} value={s.id}>
              Sem {s.number}{s.label ? ` – ${s.label}` : ''}
            </option>
          ))}
        </select>

        <select value={selSection} onChange={e => setSelSection(e.target.value)} className={selStyles} disabled={!selSemester}>
          <option value="">Section…</option>
          {(sections ?? []).filter(s => s.is_active).map(s => (
            <option key={s.id} value={s.id}>Section {s.name}</option>
          ))}
        </select>
      </div>

      {/* ── Context label ─────────────────────────────────────────────── */}
      {selSection && selectedSection && (
        <p className="text-sm text-slate-400">
          Section <span className="text-slate-200 font-medium">{selectedSection.name}</span>
          {selectedSemester && (
            <> · Semester <span className="text-slate-200 font-medium">{selectedSemester.number}{selectedSemester.label ? ` (${selectedSemester.label})` : ''}</span></>
          )}
          {selectedSection.max_strength && (
            <> · Capacity <span className="text-slate-200 font-medium">{selectedSection.max_strength}</span></>
          )}
        </p>
      )}

      {/* ── Roster table ──────────────────────────────────────────────── */}
      {!selSection ? (
        <div
          className="rounded-xl p-12 text-center text-sm text-slate-500"
          style={{ border: '1px dashed rgba(255,255,255,0.08)' }}
        >
          Select a section above to view the roster
        </div>
      ) : rosterLoading ? (
        <PageLoading message="Loading roster…" />
      ) : (roster ?? []).length === 0 ? (
        <PageEmpty icon={Users} message="No students enrolled in this section yet." />
      ) : (
        <div className="rounded-xl overflow-hidden"
          style={{ background: 'rgba(12,22,41,0.8)', border: '1px solid rgba(255,255,255,0.06)' }}>
          <table className="w-full text-sm">
            <thead style={{ background: 'rgba(255,255,255,0.02)', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
              <tr>
                {['Name', 'Email', 'ID / Reg. no.', 'Enrolled', 'Actions'].map(h => (
                  <th key={h} className="px-4 py-3 text-left text-[10px] font-semibold uppercase tracking-wide text-slate-500">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(roster ?? []).map(s => (
                <tr
                  key={s.enrollment_id}
                  className="transition-colors cursor-pointer"
                  style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}
                  onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.02)' }}
                  onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = '' }}
                  onClick={() => navigate(`/sis/students/${s.student_id}`)}
                >
                  <td className="px-4 py-3 font-medium text-slate-200">{s.full_name}</td>
                  <td className="px-4 py-3 text-slate-400 text-xs">{s.email}</td>
                  <td className="px-4 py-3 text-slate-500 text-xs">{s.identifier ?? '—'}</td>
                  <td className="px-4 py-3 text-slate-500 text-xs">
                    {new Date(s.enrolled_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => setLifecycleState({ action: 'move', enrollment: s })}
                        className="flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded font-medium"
                        style={{ background: 'rgba(99,102,241,0.08)', color: '#a5b4fc', border: '1px solid rgba(99,102,241,0.2)' }}
                      >
                        <MoveRight className="h-2.5 w-2.5" /> Move
                      </button>
                      <button
                        onClick={() => setLifecycleState({ action: 'unenroll', enrollment: s })}
                        className="flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded font-medium"
                        style={{ background: 'rgba(239,68,68,0.08)', color: '#f87171', border: '1px solid rgba(239,68,68,0.2)' }}
                      >
                        <UserMinus className="h-2.5 w-2.5" /> Unenroll
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="px-4 py-2 text-xs text-slate-600 border-t border-white/5">
            {(roster ?? []).length} student{(roster ?? []).length !== 1 ? 's' : ''} enrolled
          </div>
        </div>
      )}

      {/* ── Enroll dialog ─────────────────────────────────────────────── */}
      {showEnroll && selSection && (
        <EnrollDialog
          sectionId={selSection}
          open={showEnroll}
          onClose={() => setShowEnroll(false)}
          onEnrolled={() => qc.invalidateQueries({ queryKey: ['sis-roster', selSection] })}
        />
      )}

      {/* ── Unenroll confirm ──────────────────────────────────────────── */}
      {lifecycleState?.action === 'unenroll' && (
        <ConfirmDialog
          open
          title="Unenroll student?"
          description={`Remove ${lifecycleState.enrollment.full_name} from this section. Their enrollment record is kept and they can be re-enrolled later.`}
          confirmLabel="Unenroll"
          danger
          loading={unenrollMut.isPending}
          onConfirm={() => unenrollMut.mutate(lifecycleState.enrollment.enrollment_id)}
          onCancel={() => setLifecycleState(null)}
        />
      )}

      {/* ── Move dialog ───────────────────────────────────────────────── */}
      {lifecycleState?.action === 'move' && selSemester && (
        <MoveDialog
          enrollmentId={lifecycleState.enrollment.enrollment_id}
          currentSectionId={selSection}
          semesterId={selSemester}
          studentName={lifecycleState.enrollment.full_name}
          open
          onClose={() => setLifecycleState(null)}
          onMoved={() => {
            qc.invalidateQueries({ queryKey: ['sis-roster', selSection] })
            setLifecycleState(null)
          }}
        />
      )}
    </PageShell>
  )
}
