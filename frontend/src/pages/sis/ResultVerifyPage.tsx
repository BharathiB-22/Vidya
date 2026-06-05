import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { CheckCircle, ArrowLeft, ShieldAlert, Info, AlertCircle } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { sisApi, GraceMarkLogOut } from '@/lib/api/sis'

function ApplyGraceDialog({
  declId, open, onClose,
}: { declId: string; open: boolean; onClose: () => void }) {
  const qc = useQueryClient()
  const [studentId, setStudentId] = useState('')
  const [courseId, setCourseId] = useState('')
  const [marks, setMarks] = useState('')
  const [reason, setReason] = useState('')

  const mut = useMutation({
    mutationFn: () => sisApi.applyGraceMark(declId, {
      student_id: studentId,
      course_id: courseId,
      grace_marks_applied: parseFloat(marks),
      reason,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['grace-marks', declId] })
      onClose()
      setStudentId(''); setCourseId(''); setMarks(''); setReason('')
    },
  })

  return (
    <Dialog open={open} onOpenChange={v => !v && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Apply Grace Marks — Dean Only</DialogTitle>
        </DialogHeader>
        <div className="flex gap-2 items-start rounded-md border border-yellow-200 bg-yellow-50 p-3 text-xs text-yellow-800 mb-2">
          <ShieldAlert className="h-4 w-4 mt-0.5 shrink-0" />
          This action is logged permanently and cannot be deleted without revoke reason.
        </div>
        <div className="space-y-3 py-1">
          <div>
            <label className="text-xs font-medium">Student ID (UUID)</label>
            <Input value={studentId} onChange={e => setStudentId(e.target.value)} className="mt-1" />
          </div>
          <div>
            <label className="text-xs font-medium">Course ID (UUID)</label>
            <Input value={courseId} onChange={e => setCourseId(e.target.value)} className="mt-1" />
          </div>
          <div>
            <label className="text-xs font-medium">Grace Marks (1–10)</label>
            <Input type="number" min={1} max={10} value={marks}
              onChange={e => setMarks(e.target.value)} className="mt-1" />
          </div>
          <div>
            <label className="text-xs font-medium">Reason (min 10 chars)</label>
            <Textarea value={reason} onChange={e => setReason(e.target.value)}
              className="mt-1" rows={3} />
          </div>
          {mut.isError && (
            <p className="text-sm text-red-600">{String(mut.error)}</p>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button
            disabled={!studentId || !courseId || !marks || reason.length < 10 || mut.isPending}
            onClick={() => mut.mutate()}>
            {mut.isPending ? 'Applying…' : 'Apply Grace Marks'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default function ResultVerifyPage() {
  const { id } = useParams<{ id: string }>()
  const nav = useNavigate()
  const qc = useQueryClient()
  const [showGrace, setShowGrace] = useState(false)

  const { data: decl, isLoading, isError } = useQuery({
    queryKey: ['declaration', id],
    queryFn: () => sisApi.getDeclaration(id!),
    enabled: !!id,
  })

  const { data: graceLogs } = useQuery({
    queryKey: ['grace-marks', id],
    queryFn: () => sisApi.listGraceMarks(id!),
    enabled: !!id,
  })

  const { data: status } = useQuery({
    queryKey: ['decl-status', id],
    queryFn: () => sisApi.getComputationStatus(id!),
    enabled: !!id,
  })

  const verifyMut = useMutation({
    mutationFn: () => sisApi.verifyDeclaration(id!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['declaration', id] })
      qc.invalidateQueries({ queryKey: ['result-declarations'] })
      nav(`/sis/results/${id}`)
    },
  })

  const revokeMut = useMutation({
    mutationFn: ({ logId, reason }: { logId: string; reason: string }) =>
      sisApi.revokeGraceMark(id!, logId, reason),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['grace-marks', id] }),
  })

  if (isLoading) return <div className="p-6 text-muted-foreground">Loading…</div>
  if (isError || !decl) return <div className="p-6 text-red-600">Declaration not found.</div>

  const isDraft = decl.status === 'DRAFT'

  return (
    <PageShell>
      <button
        className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-4"
        onClick={() => nav(`/sis/results/${id}`)}
      >
        <ArrowLeft className="h-4 w-4" /> Back to Declaration
      </button>

      <PageHeader
        icon={CheckCircle}
        title="Verify Results — Dean Gate"
        subtitle={`${decl.snapshot_semester_name} · ${decl.snapshot_academic_year}`}
        action={
          <Badge variant="outline" className={`text-xs ${
            decl.status === 'DRAFT' ? 'bg-yellow-100 text-yellow-800 border-yellow-200' :
            decl.status === 'VERIFIED' ? 'bg-blue-100 text-blue-800 border-blue-200' : ''
          }`}>
            {decl.status}
          </Badge>
        }
      />

      {/* Readiness summary */}
      {status && (
        <div className={`flex gap-2 items-start rounded-md border p-3 text-sm mb-4 ${
          status.ready_to_compute
            ? 'border-green-200 bg-green-50 text-green-800'
            : 'border-orange-200 bg-orange-50 text-orange-800'
        }`}>
          <Info className="h-4 w-4 mt-0.5 shrink-0" />
          <div>
            External marks {status.external_marks_entered}/{status.total_expected} entered.
            {' '}Internal marks: {status.internal_marks_locked ? 'locked ✓' : 'not locked'}.
            {status.blocking_reasons.length > 0 && (
              <ul className="mt-1 list-disc list-inside text-xs">
                {status.blocking_reasons.map((r, i) => <li key={i}>{r}</li>)}
              </ul>
            )}
          </div>
        </div>
      )}

      {/* Grace marks section */}
      <div className="rounded-md border overflow-hidden mb-6">
        <div className="bg-muted/20 px-4 py-2 flex items-center justify-between">
          <span className="text-xs font-semibold uppercase text-muted-foreground">
            Grace Marks Log ({(graceLogs ?? []).length})
          </span>
          {isDraft && (
            <Button size="sm" variant="outline" onClick={() => setShowGrace(true)}>
              <ShieldAlert className="h-3 w-3 mr-1" />Apply Grace
            </Button>
          )}
        </div>
        {(graceLogs ?? []).length === 0 ? (
          <div className="px-4 py-6 text-center text-sm text-muted-foreground">
            No grace marks applied.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-muted/20 text-xs uppercase text-muted-foreground">
              <tr>
                <th className="px-4 py-2 text-left">Student</th>
                <th className="px-4 py-2 text-left">Course</th>
                <th className="px-4 py-2 text-center">Grace</th>
                <th className="px-4 py-2 text-left">Reason</th>
                <th className="px-4 py-2 text-center">Revoked</th>
                {isDraft && <th className="px-4 py-2" />}
              </tr>
            </thead>
            <tbody className="divide-y">
              {(graceLogs ?? []).map((g: GraceMarkLogOut) => (
                <tr key={g.id} className={g.revoked_by ? 'opacity-50' : ''}>
                  <td className="px-4 py-2 text-xs font-mono">{g.student_id.slice(0, 8)}…</td>
                  <td className="px-4 py-2 text-xs font-mono">{g.course_id.slice(0, 8)}…</td>
                  <td className="px-4 py-2 text-center font-semibold">+{Number(g.grace_marks_applied).toFixed(1)}</td>
                  <td className="px-4 py-2 text-xs text-muted-foreground">{g.reason}</td>
                  <td className="px-4 py-2 text-center text-xs">
                    {g.revoked_by ? (
                      <Badge variant="outline" className="text-xs bg-red-50 text-red-700">Revoked</Badge>
                    ) : '—'}
                  </td>
                  {isDraft && !g.revoked_by && (
                    <td className="px-4 py-2 text-right">
                      <Button size="sm" variant="ghost" className="text-xs text-destructive"
                        disabled={revokeMut.isPending}
                        onClick={() => {
                          const r = prompt('Revoke reason (min 5 chars):')
                          if (r && r.length >= 5) revokeMut.mutate({ logId: g.id, reason: r })
                        }}>
                        Revoke
                      </Button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Verify button — human gate */}
      {isDraft && (
        <div className="flex flex-col gap-3 rounded-md border border-blue-200 bg-blue-50 p-4">
          <div className="flex gap-2 items-start text-sm text-blue-800">
            <CheckCircle className="h-4 w-4 mt-0.5 shrink-0" />
            <span>
              By verifying, you (Dean) confirm that results have been reviewed and are correct.
              This advances the declaration to VERIFIED status for publication.
            </span>
          </div>
          <div className="flex gap-2">
            <Button onClick={() => verifyMut.mutate()} disabled={verifyMut.isPending}>
              {verifyMut.isPending ? 'Verifying…' : 'Verify Results'}
            </Button>
          </div>
          {verifyMut.isError && (
            <div className="flex gap-2 items-start text-sm text-red-700">
              <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
              {String(verifyMut.error)}
            </div>
          )}
        </div>
      )}

      {decl.status === 'VERIFIED' && (
        <div className="flex gap-2 items-start rounded-md border border-green-200 bg-green-50 p-3 text-sm text-green-800">
          <CheckCircle className="h-4 w-4 mt-0.5 shrink-0" />
          Results verified at {decl.verified_at ? new Date(decl.verified_at).toLocaleString() : '—'}. Ready for publication.
        </div>
      )}

      <ApplyGraceDialog declId={id!} open={showGrace} onClose={() => setShowGrace(false)} />
    </PageShell>
  )
}
