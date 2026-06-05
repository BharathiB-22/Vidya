import { useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ClipboardList, ArrowLeft, CheckCircle, RefreshCw, Award,
  BarChart2, Lock, RotateCcw, AlertCircle, Info,
} from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'
import { sisApi } from '@/lib/api/sis'
import { useAuth } from '@/lib/auth'

const STATUS_COLORS: Record<string, string> = {
  DRAFT:     'bg-yellow-100 text-yellow-800 border-yellow-200',
  VERIFIED:  'bg-blue-100   text-blue-800   border-blue-200',
  PUBLISHED: 'bg-green-100  text-green-800  border-green-200',
  LOCKED:    'bg-gray-100   text-gray-700   border-gray-300',
}

function RevertDialog({ open, onClose, onConfirm, loading }: {
  open: boolean; onClose: () => void; onConfirm: (r: string) => void; loading: boolean
}) {
  const [reason, setReason] = useState('')
  return (
    <Dialog open={open} onOpenChange={v => !v && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader><DialogTitle>Revert to Draft</DialogTitle></DialogHeader>
        <div className="py-2">
          <label className="text-xs font-medium">Reason (required)</label>
          <Textarea value={reason} onChange={e => setReason(e.target.value)}
            className="mt-1" rows={3} placeholder="Why are you reverting this declaration?" />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button variant="destructive" disabled={reason.length < 5 || loading}
            onClick={() => onConfirm(reason)}>
            {loading ? 'Reverting…' : 'Revert to Draft'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default function ResultDeclarationDetailPage() {
  const { id } = useParams<{ id: string }>()
  const nav = useNavigate()
  const qc = useQueryClient()
  const { user } = useAuth()
  const [showRevert, setShowRevert] = useState(false)

  const { data: decl, isLoading, isError } = useQuery({
    queryKey: ['declaration', id],
    queryFn: () => sisApi.getDeclaration(id!),
    enabled: !!id,
  })

  const { data: status } = useQuery({
    queryKey: ['decl-status', id],
    queryFn: () => sisApi.getComputationStatus(id!),
    enabled: !!id && !!decl && ['DRAFT', 'VERIFIED'].includes(decl.status),
  })

  const computeMut = useMutation({
    mutationFn: () => sisApi.computeResults(id!, false),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['declaration', id] }),
  })

  const computeSgpaMut = useMutation({
    mutationFn: () => sisApi.computeSgpaCgpa(id!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['declaration', id] }),
  })

  const computeRanksMut = useMutation({
    mutationFn: () => sisApi.computeRanks(id!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['declaration', id] }),
  })

  const publishMut = useMutation({
    mutationFn: () => sisApi.publishDeclaration(id!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['declaration', id] })
      qc.invalidateQueries({ queryKey: ['result-declarations'] })
    },
  })

  const lockMut = useMutation({
    mutationFn: () => sisApi.lockDeclaration(id!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['declaration', id] })
      qc.invalidateQueries({ queryKey: ['result-declarations'] })
    },
  })

  const revertMut = useMutation({
    mutationFn: (reason: string) => sisApi.revertToDraft(id!, reason),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['declaration', id] })
      qc.invalidateQueries({ queryKey: ['result-declarations'] })
      setShowRevert(false)
    },
  })

  if (isLoading) return <div className="p-6 text-muted-foreground">Loading declaration…</div>
  if (isError || !decl) return <div className="p-6 text-red-600">Declaration not found.</div>

  const isDraft     = decl.status === 'DRAFT'
  const isVerified  = decl.status === 'VERIFIED'
  const isPublished = decl.status === 'PUBLISHED'
  const isLocked    = decl.status === 'LOCKED'
  const isAdmin     = user?.role === 'ADMIN'
  const isDean      = user?.role === 'DEAN'
  const isManager   = isAdmin || isDean

  return (
    <PageShell>
      <button
        className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-4"
        onClick={() => nav('/sis/results')}
      >
        <ArrowLeft className="h-4 w-4" /> All Declarations
      </button>

      <PageHeader
        icon={ClipboardList}
        title={decl.title ?? `${decl.snapshot_semester_name} Results`}
        subtitle={`${decl.snapshot_academic_year} · ${decl.declaration_type} · Policy: ${decl.snapshot_grading_policy_name}`}
        action={
          <Badge variant="outline" className={`text-xs ${STATUS_COLORS[decl.status] ?? ''}`}>
            {decl.status}
          </Badge>
        }
      />

      {/* Computation status banner */}
      {status && isDraft && (
        <div className={`flex gap-2 items-start rounded-md border p-3 text-sm mb-4 ${
          status.ready_to_compute
            ? 'border-green-200 bg-green-50 text-green-800'
            : 'border-yellow-200 bg-yellow-50 text-yellow-800'
        }`}>
          <Info className="h-4 w-4 mt-0.5 shrink-0" />
          <div>
            <div className="font-medium">
              {status.ready_to_compute ? 'Ready to compute' : 'Not ready to compute'}
            </div>
            <div className="text-xs mt-0.5">
              External marks: {status.external_marks_entered} / {status.total_expected} entered
              ({status.external_marks_pending} pending)
            </div>
            {status.blocking_reasons.length > 0 && (
              <ul className="mt-1 list-disc list-inside text-xs">
                {status.blocking_reasons.map((r, i) => <li key={i}>{r}</li>)}
              </ul>
            )}
          </div>
        </div>
      )}

      {/* Action row */}
      <div className="flex flex-wrap gap-2 mb-6">
        {isDraft && isManager && (
          <Button size="sm" onClick={() => computeMut.mutate()}
            disabled={computeMut.isPending}>
            <RefreshCw className={`h-4 w-4 mr-1 ${computeMut.isPending ? 'animate-spin' : ''}`} />
            {computeMut.isPending ? 'Computing…' : 'Compute Results'}
          </Button>
        )}
        {isDraft && isManager && (
          <Button size="sm" variant="outline" onClick={() => computeSgpaMut.mutate()}
            disabled={computeSgpaMut.isPending}>
            {computeSgpaMut.isPending ? 'Computing…' : 'Compute SGPA/CGPA'}
          </Button>
        )}
        {isDraft && isManager && (
          <Button size="sm" variant="outline" onClick={() => computeRanksMut.mutate()}
            disabled={computeRanksMut.isPending}>
            {computeRanksMut.isPending ? 'Computing…' : 'Compute Ranks'}
          </Button>
        )}
        {isDraft && isDean && (
          <Button size="sm" variant="outline" asChild>
            <Link to={`/sis/results/${id}/verify`}>
              <CheckCircle className="h-4 w-4 mr-1" />Verify
            </Link>
          </Button>
        )}
        {isVerified && isManager && (
          <Button size="sm" onClick={() => publishMut.mutate()}
            disabled={publishMut.isPending}>
            {publishMut.isPending ? 'Publishing…' : 'Publish Results'}
          </Button>
        )}
        {isPublished && isAdmin && (
          <Button size="sm" variant="outline" onClick={() => lockMut.mutate()}
            disabled={lockMut.isPending}>
            <Lock className="h-4 w-4 mr-1" />
            {lockMut.isPending ? 'Locking…' : 'Lock'}
          </Button>
        )}
        {!isLocked && isManager && (
          <Button size="sm" variant="ghost" className="text-destructive hover:text-destructive"
            onClick={() => setShowRevert(true)}>
            <RotateCcw className="h-4 w-4 mr-1" />Revert to Draft
          </Button>
        )}
      </div>

      {/* Navigation links */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">
        {isManager && (
          <Link to={`/sis/results/${id}/grade-cards`}
            className="flex items-center gap-3 rounded-md border p-4 hover:bg-muted/10">
            <Award className="h-5 w-5 text-blue-600 shrink-0" />
            <div>
              <div className="font-medium text-sm">Grade Cards</div>
              <div className="text-xs text-muted-foreground">View all student grade cards</div>
            </div>
          </Link>
        )}
        <Link to={`/sis/results/${id}/ranks`}
          className="flex items-center gap-3 rounded-md border p-4 hover:bg-muted/10">
          <BarChart2 className="h-5 w-5 text-green-600 shrink-0" />
          <div>
            <div className="font-medium text-sm">Rank List</div>
            <div className="text-xs text-muted-foreground">Program and section rankings</div>
          </div>
        </Link>
        {isDraft && isDean && (
          <Link to={`/sis/results/${id}/verify`}
            className="flex items-center gap-3 rounded-md border p-4 hover:bg-muted/10">
            <CheckCircle className="h-5 w-5 text-yellow-600 shrink-0" />
            <div>
              <div className="font-medium text-sm">Verify Results</div>
              <div className="text-xs text-muted-foreground">Review, apply grace marks, verify</div>
            </div>
          </Link>
        )}
      </div>

      {/* Declaration metadata */}
      <div className="rounded-md border overflow-hidden">
        <div className="bg-muted/20 px-4 py-2 text-xs font-semibold uppercase text-muted-foreground">
          Declaration Details
        </div>
        <dl className="divide-y text-sm">
          {[
            ['Academic Year',    decl.snapshot_academic_year],
            ['Semester',         decl.snapshot_semester_name],
            ['Grading Policy',   decl.snapshot_grading_policy_name],
            ['Type',             decl.declaration_type],
            ['Internal Marks',   decl.internal_marks_required ? 'Required' : 'Not required'],
            ['Notes',            decl.notes ?? '—'],
            ['Verified at',      decl.verified_at ? new Date(decl.verified_at).toLocaleString() : '—'],
            ['Published at',     decl.published_at ? new Date(decl.published_at).toLocaleString() : '—'],
            ['Locked at',        decl.locked_at ? new Date(decl.locked_at).toLocaleString() : '—'],
            ['Created at',       new Date(decl.created_at).toLocaleString()],
          ].map(([label, value]) => (
            <div key={label} className="grid grid-cols-3 px-4 py-2 gap-4">
              <dt className="text-muted-foreground">{label}</dt>
              <dd className="col-span-2">{value}</dd>
            </div>
          ))}
        </dl>
      </div>

      {/* Error banners */}
      {(computeMut.isError || publishMut.isError || lockMut.isError) && (
        <div className="flex gap-2 items-start rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700 mt-4">
          <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
          {String(computeMut.error ?? publishMut.error ?? lockMut.error)}
        </div>
      )}

      <RevertDialog
        open={showRevert}
        onClose={() => setShowRevert(false)}
        onConfirm={reason => revertMut.mutate(reason)}
        loading={revertMut.isPending}
      />
    </PageShell>
  )
}
