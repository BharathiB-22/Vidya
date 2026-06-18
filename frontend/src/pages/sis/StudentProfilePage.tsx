import { useState } from 'react'
import { useNavigate, useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, UserCircle2, MoveRight, UserMinus, GraduationCap, LayoutList, Activity, ChevronDown } from 'lucide-react'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { PageShell } from '@/components/shell/PageShell'
import { PageLoading } from '@/components/shared/PageLoading'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { addToast } from '@/hooks/useToast'
import { getErrorMessage } from '@/lib/api'
import { sisApi } from '@/lib/api/sis'
import { academicsApi } from '@/lib/api/academics'
import { useCurrentUser } from '@/hooks/useCurrentUser'
import type { StudentProfile, LifecycleStatusOut } from '@/lib/api/sis'

// ---------------------------------------------------------------------------
// Lifecycle helpers
// ---------------------------------------------------------------------------

const STATUS_COLORS: Record<string, { bg: string; color: string; border: string }> = {
  APPLICANT: { bg: 'rgba(59,130,246,0.12)', color: '#93c5fd', border: 'rgba(59,130,246,0.25)' },
  ENROLLED:  { bg: 'rgba(139,92,246,0.12)', color: '#a78bfa', border: 'rgba(139,92,246,0.25)' },
  ACTIVE:    { bg: 'rgba(34,197,94,0.12)',  color: '#4ade80', border: 'rgba(34,197,94,0.25)'  },
  DETAINED:  { bg: 'rgba(251,191,36,0.12)', color: '#fbbf24', border: 'rgba(251,191,36,0.25)' },
  GRADUATED: { bg: 'rgba(99,102,241,0.12)', color: '#818cf8', border: 'rgba(99,102,241,0.25)' },
  ALUMNI:    { bg: 'rgba(20,184,166,0.12)', color: '#2dd4bf', border: 'rgba(20,184,166,0.25)' },
  WITHDRAWN: { bg: 'rgba(239,68,68,0.12)',  color: '#f87171', border: 'rgba(239,68,68,0.25)'  },
  ARCHIVED:  { bg: 'rgba(100,116,139,0.12)',color: '#94a3b8', border: 'rgba(100,116,139,0.25)'},
}

function LifecycleBadge({ status }: { status: string }) {
  const c = STATUS_COLORS[status] ?? STATUS_COLORS.ACTIVE
  return (
    <span
      className="inline-flex items-center text-xs font-semibold px-2 py-0.5 rounded"
      style={{ background: c.bg, color: c.color, border: `1px solid ${c.border}` }}
    >
      {status}
    </span>
  )
}

function formatDt(iso: string) {
  return new Date(iso).toLocaleString(undefined, { month: 'short', day: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

// ---------------------------------------------------------------------------
// Lifecycle panel (shown to ADMIN / DEAN only)
// ---------------------------------------------------------------------------

function LifecyclePanel({
  studentId,
  canManage,
}: {
  studentId: string
  canManage: boolean
}) {
  const qc = useQueryClient()
  const [selectedStatus, setSelectedStatus] = useState('')
  const [reason, setReason]                 = useState('')
  const [showHistory, setShowHistory]       = useState(false)

  const { data, isLoading } = useQuery<LifecycleStatusOut>({
    queryKey: ['sis-lifecycle', studentId],
    queryFn:  () => sisApi.getStudentLifecycle(studentId),
    enabled:  canManage,
  })

  const transitionMut = useMutation({
    mutationFn: () => sisApi.transitionStudentLifecycle(studentId, selectedStatus, reason || undefined),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['sis-lifecycle', studentId] })
      qc.invalidateQueries({ queryKey: ['sis-student-profile', studentId] })
      addToast(res.message, 'success')
      setSelectedStatus('')
      setReason('')
    },
    onError: (e) => addToast(getErrorMessage(e), 'error'),
  })

  if (!canManage) return null
  if (isLoading || !data) return (
    <div className="rounded-xl px-6 py-4 bg-white border border-gray-200 shadow-sm">
      <p className="text-sm text-gray-400">Loading lifecycle…</p>
    </div>
  )

  return (
    <div className="rounded-xl px-6 py-4 space-y-3 bg-white border border-gray-200 shadow-sm">

      <div className="flex items-center gap-2 pb-2 border-b border-gray-100">
        <Activity className="h-4 w-4 text-gray-400" />
        <h3 className="text-sm font-semibold text-gray-700">Lifecycle Status</h3>
      </div>

      {/* Current status */}
      <div className="flex items-center justify-between py-1">
        <span className="text-sm text-gray-500">Current status</span>
        <LifecycleBadge status={data.current_status} />
      </div>

      {/* Transition picker */}
      {data.allowed_next.length > 0 && (
        <div className="space-y-2 pt-1">
          <p className="text-xs text-gray-500">Change status (human ratification required):</p>
          <Select value={selectedStatus || undefined} onValueChange={setSelectedStatus}>
            <SelectTrigger className="w-full"><SelectValue placeholder="Select new status…" /></SelectTrigger>
            <SelectContent>
              {data.allowed_next.map(s => (
                <SelectItem key={s} value={s}>{s}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          {selectedStatus && (
            <>
              <input
                type="text"
                placeholder="Reason (optional)"
                value={reason}
                onChange={e => setReason(e.target.value)}
                className="w-full px-3 py-2 text-sm rounded-lg bg-gray-50 border border-gray-200 text-gray-900 placeholder:text-gray-400"
              />
              <Button
                size="sm"
                onClick={() => transitionMut.mutate()}
                disabled={transitionMut.isPending}
                className="w-full"
              >
                {transitionMut.isPending ? 'Applying…' : `Confirm → ${selectedStatus}`}
              </Button>
            </>
          )}
        </div>
      )}

      {data.current_status === 'ARCHIVED' && (
        <p className="text-xs text-gray-500 py-1">This student is archived. No further transitions available.</p>
      )}

      {/* History toggle */}
      {data.history.length > 0 && (
        <div className="pt-2">
          <button
            onClick={() => setShowHistory(v => !v)}
            className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700 transition-colors"
          >
            <ChevronDown size={12} className={showHistory ? 'rotate-180 transition-transform' : 'transition-transform'} />
            {showHistory ? 'Hide' : 'Show'} history ({data.history.length})
          </button>
          {showHistory && (
            <div className="mt-2 space-y-1">
              {data.history.map(h => (
                <div key={h.id} className="text-xs text-gray-500 flex items-start gap-2 py-1 border-b border-gray-50 last:border-0">
                  <span className="shrink-0 tabular-nums text-gray-400">{formatDt(h.changed_at)}</span>
                  <span>
                    {h.from_status
                      ? <><LifecycleBadge status={h.from_status} /> → <LifecycleBadge status={h.to_status} /></>
                      : <>Set to <LifecycleBadge status={h.to_status} /></>
                    }
                    {h.reason && <span className="ml-1 text-gray-400">— {h.reason}</span>}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Shared sub-components
// ---------------------------------------------------------------------------

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between py-3 border-b border-gray-100 last:border-0">
      <span className="text-sm text-gray-500">{label}</span>
      <span className="text-sm font-semibold text-gray-900">{value}</span>
    </div>
  )
}

function Card({ title, icon: Icon, children }: { title: string; icon: typeof UserCircle2; children: React.ReactNode }) {
  return (
    <div className="rounded-xl px-6 py-4 space-y-1 bg-white border border-gray-200 shadow-sm">
      <div className="flex items-center gap-2 pb-2 border-b border-gray-100">
        <Icon className="h-4 w-4 text-gray-400" />
        <h3 className="text-sm font-semibold text-gray-700">{title}</h3>
      </div>
      {children}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Move-section dialog
// ---------------------------------------------------------------------------

function MoveSectionDialog({
  enrollmentId,
  semesterId,
  currentSectionId,
  open,
  onClose,
  onMoved,
}: {
  enrollmentId: string
  semesterId: string
  currentSectionId: string
  open: boolean
  onClose: () => void
  onMoved: () => void
}) {
  const [targetId, setTargetId] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const { data: sections } = useQuery({
    queryKey: ['acad-sections', semesterId],
    queryFn:  () => academicsApi.listSections(semesterId),
    enabled:  !!semesterId,
  })

  const others = (sections ?? []).filter(s => s.id !== currentSectionId && s.is_active)

  async function move() {
    if (!targetId) return
    setBusy(true); setErr('')
    try {
      await sisApi.moveStudent(enrollmentId, targetId)
      addToast('Student moved to new section.', 'success')
      onMoved()
    } catch (e) { setErr(getErrorMessage(e)) }
    finally { setBusy(false) }
  }

  return (
    <Dialog open={open} onOpenChange={v => { if (!v) { onClose(); setTargetId('') } }}>
      <DialogContent className="max-w-sm">
        <DialogHeader><DialogTitle>Move to another section</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <Select value={targetId || undefined} onValueChange={setTargetId}>
            <SelectTrigger className="w-full"><SelectValue placeholder="Select section…" /></SelectTrigger>
            <SelectContent>
              {others.map(s => <SelectItem key={s.id} value={s.id}>Section {s.name}</SelectItem>)}
            </SelectContent>
          </Select>
          {others.length === 0 && <p className="text-xs text-slate-500">No other active sections in this semester.</p>}
          {err && <p className="text-xs text-red-400">{err}</p>}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={move} disabled={!targetId || busy}>{busy ? 'Moving…' : 'Move'}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function StudentProfilePage() {
  const { student_id } = useParams<{ student_id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const currentUser = useCurrentUser()

  const [showMove,      setShowMove]      = useState(false)
  const [showUnenroll,  setShowUnenroll]  = useState(false)

  const canManage = currentUser?.role === 'ADMIN' || currentUser?.role === 'DEAN'

  const { data: profile, isLoading } = useQuery<StudentProfile>({
    queryKey: ['sis-student-profile', student_id],
    queryFn:  () => sisApi.getStudentProfile(student_id!),
    enabled:  !!student_id,
  })

  const unenrollMut = useMutation({
    mutationFn: () => sisApi.unenrollStudent(profile!.enrollment!.enrollment_id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sis-student-profile', student_id] })
      addToast('Student unenrolled.', 'success')
      setShowUnenroll(false)
    },
    onError: (e) => { addToast(getErrorMessage(e), 'error'); setShowUnenroll(false) },
  })

  if (isLoading) return <PageLoading message="Loading student profile…" />
  if (!profile) return (
    <PageShell>
      <p className="text-center py-16 text-slate-500">Student not found.</p>
    </PageShell>
  )

  const hasEnrollment = !!profile.enrollment

  return (
    <PageShell width="sm">

      {/* Back navigation */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => navigate(-1)}
          className="p-1.5 rounded-lg text-gray-400 hover:bg-gray-100 hover:text-gray-600 transition-colors"
          aria-label="Back"
        >
          <ArrowLeft className="h-5 w-5" />
        </button>
        <div>
          <h2 className="text-xl font-bold text-gray-900">{profile.full_name}</h2>
          <p className="text-sm text-gray-500">{profile.email}</p>
        </div>
        <Link
          to="/sis/roster"
          className="ml-auto text-xs text-gray-400 hover:text-gray-600 transition-colors"
        >
          ← Roster
        </Link>
      </div>

      {/* Student info */}
      <Card title="Student" icon={UserCircle2}>
        <InfoRow label="Full name" value={
          <span className="font-semibold text-gray-900">{profile.full_name}</span>
        } />
        <InfoRow label="Email" value={
          <span className="text-gray-700">{profile.email}</span>
        } />
        <InfoRow label="Institution email" value={
          profile.institution_email
            ? <span className="font-mono font-semibold text-indigo-600">{profile.institution_email}</span>
            : <span className="text-xs text-amber-600 font-medium">Not generated yet</span>
        } />
        {profile.usn && (
          <InfoRow label="USN" value={
            <span className="font-mono font-bold text-indigo-700">{profile.usn}</span>
          } />
        )}
        {profile.admission_year && (
          <InfoRow label="Admission year" value={String(profile.admission_year)} />
        )}
      </Card>

      {/* Academic path */}
      <Card title="Academic path" icon={GraduationCap}>
        {profile.program ? (
          <>
            <InfoRow label="Program"    value={`${profile.program.name} (${profile.program.code})`} />
            <InfoRow label="Degree"     value={profile.program.degree_type} />
            <InfoRow label="Department" value={profile.department ? `${profile.department.name} (${profile.department.code})` : '—'} />
            <InfoRow label="Batch"      value={profile.batch ? `${profile.batch.name} (${profile.batch.start_year}–${profile.batch.end_year})` : '—'} />
          </>
        ) : (
          <p className="py-3 text-sm text-slate-500">No program assigned.</p>
        )}
      </Card>

      {/* Current enrollment */}
      <Card title="Current enrollment" icon={LayoutList}>
        {hasEnrollment ? (
          <>
            <InfoRow
              label="Section"
              value={`Section ${profile.enrollment!.section.name}`}
            />
            <InfoRow
              label="Semester"
              value={`Sem ${profile.enrollment!.semester.number}${profile.enrollment!.semester.label ? ` – ${profile.enrollment!.semester.label}` : ''}`}
            />
          </>
        ) : (
          <p className="py-3 text-sm text-slate-500">Not currently enrolled in any section.</p>
        )}
      </Card>

      {/* Lifecycle panel — ADMIN / DEAN only */}
      {student_id && (
        <LifecyclePanel studentId={student_id} canManage={canManage} />
      )}

      {/* Enrollment actions */}
      {hasEnrollment && (
        <div className="rounded-xl p-5 space-y-3 bg-white border border-gray-200 shadow-sm">
          <h3 className="text-sm font-semibold text-gray-700">Enrollment actions</h3>

          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-800">Move to another section</p>
              <p className="text-xs text-gray-500 mt-0.5">Transfer within the same semester.</p>
            </div>
            <button
              onClick={() => setShowMove(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium bg-indigo-50 border border-indigo-200 text-indigo-700 hover:bg-indigo-100 transition-colors"
            >
              <MoveRight className="h-3.5 w-3.5" /> Move
            </button>
          </div>

          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-800">Unenroll</p>
              <p className="text-xs text-gray-500 mt-0.5">Remove from section. Record is kept; re-enrollment is possible.</p>
            </div>
            <button
              onClick={() => setShowUnenroll(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium bg-red-50 border border-red-200 text-red-600 hover:bg-red-100 transition-colors"
            >
              <UserMinus className="h-3.5 w-3.5" /> Unenroll
            </button>
          </div>
        </div>
      )}

      {/* Move dialog */}
      {showMove && profile.enrollment && (
        <MoveSectionDialog
          enrollmentId={profile.enrollment.enrollment_id}
          semesterId={profile.enrollment.semester.id}
          currentSectionId={profile.enrollment.section.id}
          open={showMove}
          onClose={() => setShowMove(false)}
          onMoved={() => {
            qc.invalidateQueries({ queryKey: ['sis-student-profile', student_id] })
            setShowMove(false)
          }}
        />
      )}

      {/* Unenroll confirm */}
      <ConfirmDialog
        open={showUnenroll}
        title="Unenroll student?"
        description={`Remove ${profile.full_name} from their current section. Their enrollment record is preserved and they can be re-enrolled later.`}
        confirmLabel="Unenroll"
        danger
        loading={unenrollMut.isPending}
        onConfirm={() => unenrollMut.mutate()}
        onCancel={() => setShowUnenroll(false)}
      />
    </PageShell>
  )
}
