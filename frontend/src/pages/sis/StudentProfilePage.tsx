import { useState } from 'react'
import { useNavigate, useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, UserCircle2, MoveRight, UserMinus, GraduationCap, LayoutList } from 'lucide-react'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { PageShell } from '@/components/shell/PageShell'
import { PageLoading } from '@/components/shared/PageLoading'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { addToast } from '@/hooks/useToast'
import { getErrorMessage } from '@/lib/api'
import { sisApi } from '@/lib/api/sis'
import { academicsApi } from '@/lib/api/academics'
import type { StudentProfile } from '@/lib/api/sis'

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div
      className="flex items-center justify-between py-3"
      style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}
    >
      <span className="text-sm text-slate-500">{label}</span>
      <span className="text-sm text-slate-200 font-medium">{value}</span>
    </div>
  )
}

function Card({ title, icon: Icon, children }: { title: string; icon: typeof UserCircle2; children: React.ReactNode }) {
  return (
    <div className="rounded-xl px-6 py-4 space-y-1"
      style={{ background: 'rgba(12,22,41,0.85)', border: '1px solid rgba(255,255,255,0.08)' }}>
      <div className="flex items-center gap-2 pb-2" style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
        <Icon className="h-4 w-4 text-slate-500" />
        <h3 className="text-sm font-semibold text-slate-400">{title}</h3>
      </div>
      {children}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Move-section dialog (same as in RosterPage but scoped to profile)
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
          <select
            value={targetId}
            onChange={e => setTargetId(e.target.value)}
            className="w-full px-3 py-2 text-sm rounded-lg bg-white/5 border border-white/10 text-slate-200"
          >
            <option value="">Select section…</option>
            {others.map(s => <option key={s.id} value={s.id}>Section {s.name}</option>)}
          </select>
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

  const [showMove,      setShowMove]      = useState(false)
  const [showUnenroll,  setShowUnenroll]  = useState(false)

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
          className="p-1.5 rounded-lg text-slate-600 hover:bg-white/6 hover:text-slate-300 transition-colors"
          aria-label="Back"
        >
          <ArrowLeft className="h-5 w-5" />
        </button>
        <div>
          <h2 className="text-xl font-semibold text-slate-100">{profile.full_name}</h2>
          <p className="text-xs text-slate-500">{profile.email}</p>
        </div>
        <Link
          to="/sis/roster"
          className="ml-auto text-xs text-slate-500 hover:text-slate-300 transition-colors"
        >
          ← Roster
        </Link>
      </div>

      {/* Student info */}
      <Card title="Student" icon={UserCircle2}>
        <InfoRow label="Full name"   value={profile.full_name} />
        <InfoRow label="Email"       value={profile.email} />
        <InfoRow label="Identifier"  value={profile.identifier ?? '—'} />
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

      {/* Actions */}
      {hasEnrollment && (
        <div
          className="rounded-xl p-5 space-y-3"
          style={{ background: 'rgba(12,22,41,0.85)', border: '1px solid rgba(255,255,255,0.08)' }}
        >
          <h3 className="text-sm font-semibold text-slate-400">Enrollment actions</h3>

          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-slate-200">Move to another section</p>
              <p className="text-xs text-slate-500 mt-0.5">Transfer within the same semester.</p>
            </div>
            <button
              onClick={() => setShowMove(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium"
              style={{ background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.25)', color: '#a5b4fc' }}
            >
              <MoveRight className="h-3.5 w-3.5" /> Move
            </button>
          </div>

          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-slate-200">Unenroll</p>
              <p className="text-xs text-slate-500 mt-0.5">Remove from section. Record is kept; re-enrollment is possible.</p>
            </div>
            <button
              onClick={() => setShowUnenroll(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium"
              style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)', color: '#f87171' }}
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
