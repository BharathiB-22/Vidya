import { useMemo, useState } from 'react'
import {
  Network, Users, RefreshCw, Ban, Filter,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog'
import { PageLoading } from '@/components/shared/PageLoading'
import { PageError } from '@/components/shared/PageError'
import { PageEmpty } from '@/components/shared/PageEmpty'
import { addToast } from '@/hooks/useToast'
import { getErrorMessage } from '@/lib/api'
import { useCurrentUser } from '@/hooks/useCurrentUser'
import {
  useAssignments,
  useReassignAssignment,
  useCancelAssignment,
} from '@/hooks/evaluationAssignments'
import type {
  AssignmentStatus, AssignmentType, EvaluationAssignment,
} from '@/types/evaluationAssignment'
import { StatusBadge, TypeBadge, TYPE_LABELS, formatDateTime, workItemCode } from './assignmentShared'

const STATUS_FILTERS: (AssignmentStatus | 'ALL')[] = [
  'ALL', 'ASSIGNED', 'IN_PROGRESS', 'SUBMITTED', 'COMPLETED', 'CANCELLED', 'REASSIGNED',
]
const TYPE_FILTERS: (AssignmentType | 'ALL')[] = [
  'ALL', 'REGULAR', 'DOUBLE_EVALUATION', 'MODERATION', 'REVALUATION', 'DIGITAL_SUBJECTIVE',
]

interface Props {
  /** 'admin' enables allocation + cancel; 'dean' is monitor + reassign only. */
  mode: 'admin' | 'dean'
}

export default function AssignmentManagementPage({ mode }: Props) {
  const user = useCurrentUser()
  const isAdmin = mode === 'admin' || user?.role === 'ADMIN'

  const [status, setStatus] = useState<AssignmentStatus | 'ALL'>('ALL')
  const [type, setType] = useState<AssignmentType | 'ALL'>('ALL')

  const params = useMemo(() => ({
    status: status === 'ALL' ? undefined : status,
    assignment_type: type === 'ALL' ? undefined : type,
    limit: 200,
  }), [status, type])

  const { data, isLoading, isError, refetch } = useAssignments(params)

  const reassign = useReassignAssignment()
  const cancel = useCancelAssignment()

  const [reassignTarget, setReassignTarget] = useState<EvaluationAssignment | null>(null)
  const [newEvaluator, setNewEvaluator] = useState('')
  const [reassignReason, setReassignReason] = useState('')
  const [cancelTarget, setCancelTarget] = useState<EvaluationAssignment | null>(null)
  const [cancelReason, setCancelReason] = useState('')

  const submitReassign = async () => {
    if (!reassignTarget) return
    try {
      await reassign.mutateAsync({
        id: reassignTarget.id,
        payload: { new_evaluator_id: newEvaluator.trim(), reason: reassignReason.trim() },
      })
      addToast('Assignment reassigned', 'success')
      setReassignTarget(null); setNewEvaluator(''); setReassignReason('')
    } catch (e) { addToast(getErrorMessage(e), 'error') }
  }

  const submitCancel = async () => {
    if (!cancelTarget) return
    try {
      await cancel.mutateAsync({ id: cancelTarget.id, payload: { reason: cancelReason.trim() } })
      addToast('Assignment cancelled', 'success')
      setCancelTarget(null); setCancelReason('')
    } catch (e) { addToast(getErrorMessage(e), 'error') }
  }

  const rows = data?.items ?? []
  const isActive = (s: AssignmentStatus) => ['ASSIGNED', 'IN_PROGRESS', 'SUBMITTED'].includes(s)

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-5">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600">
          <Network className="w-5 h-5" />
        </div>
        <div className="flex-1">
          <h1 className="text-xl font-semibold text-gray-900">
            Evaluation Assignments {isAdmin ? '· Management' : '· Monitoring'}
          </h1>
          <p className="text-sm text-gray-500">
            {isAdmin
              ? 'Allocate, auto-balance, reassign and monitor evaluation workload.'
              : 'Monitor evaluation workload and rebalance across faculty.'}
          </p>
        </div>
        <Button variant="ghost" size="sm" onClick={() => refetch()} className="gap-1.5">
          <RefreshCw className="w-4 h-4" /> Refresh
        </Button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-gray-200 bg-white p-3">
        <Filter className="w-4 h-4 text-gray-400" />
        <select value={status} onChange={(e) => setStatus(e.target.value as AssignmentStatus | 'ALL')}
          className="text-sm border border-gray-200 rounded-md px-2 py-1.5">
          {STATUS_FILTERS.map((s) => <option key={s} value={s}>{s === 'ALL' ? 'All statuses' : s.replace('_', ' ')}</option>)}
        </select>
        <select value={type} onChange={(e) => setType(e.target.value as AssignmentType | 'ALL')}
          className="text-sm border border-gray-200 rounded-md px-2 py-1.5">
          {TYPE_FILTERS.map((t) => <option key={t} value={t}>{t === 'ALL' ? 'All types' : TYPE_LABELS[t as AssignmentType]}</option>)}
        </select>
        <span className="ml-auto text-xs text-gray-400">{rows.length} shown</span>
      </div>

      {isLoading ? (
        <PageLoading />
      ) : isError ? (
        <PageError onRetry={() => refetch()} />
      ) : rows.length === 0 ? (
        <PageEmpty icon={Users} title="No assignments" message="No assignments match these filters." />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 text-left text-xs uppercase tracking-wide text-gray-400">
                <th className="px-4 py-2.5 font-medium">Work Item</th>
                <th className="px-4 py-2.5 font-medium">Type</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
                <th className="px-4 py-2.5 font-medium">Evaluator</th>
                <th className="px-4 py-2.5 font-medium">Assigned</th>
                <th className="px-4 py-2.5 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((a) => (
                <tr key={a.id} className="border-b border-gray-50 last:border-0 hover:bg-gray-50/60">
                  <td className="px-4 py-2.5 font-mono text-gray-800">
                    {workItemCode(a)}
                    {a.evaluation_round !== 'NONE' && (
                      <Badge className="ml-2 bg-indigo-50 text-indigo-600 text-[10px]">{a.evaluation_round}</Badge>
                    )}
                  </td>
                  <td className="px-4 py-2.5"><TypeBadge type={a.assignment_type} /></td>
                  <td className="px-4 py-2.5"><StatusBadge status={a.status} /></td>
                  <td className="px-4 py-2.5 font-mono text-xs text-gray-500">{a.evaluator_id.slice(0, 8)}</td>
                  <td className="px-4 py-2.5 text-xs text-gray-500">{formatDateTime(a.assigned_at)}</td>
                  <td className="px-4 py-2.5">
                    <div className="flex justify-end gap-1">
                      {isActive(a.status) && (
                        <Button variant="ghost" size="sm" className="h-7 gap-1 text-indigo-600"
                          onClick={() => setReassignTarget(a)}>
                          <RefreshCw className="w-3.5 h-3.5" /> Reassign
                        </Button>
                      )}
                      {isAdmin && isActive(a.status) && (
                        <Button variant="ghost" size="sm" className="h-7 gap-1 text-red-500"
                          onClick={() => setCancelTarget(a)}>
                          <Ban className="w-3.5 h-3.5" /> Cancel
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Reassign dialog */}
      <Dialog open={Boolean(reassignTarget)} onOpenChange={(o) => { if (!o) setReassignTarget(null) }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Reassign assignment</DialogTitle>
            <DialogDescription>
              The existing assignment is preserved as REASSIGNED for audit; a fresh one is
              created for the new evaluator.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <label className="text-xs text-gray-500">New evaluator user ID</label>
              <Input value={newEvaluator} onChange={(e) => setNewEvaluator(e.target.value)}
                placeholder="evaluator UUID" className="mt-1 font-mono text-sm" />
            </div>
            <div>
              <label className="text-xs text-gray-500">Reason</label>
              <Input value={reassignReason} onChange={(e) => setReassignReason(e.target.value)}
                placeholder="Why is this being reassigned?" className="mt-1" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setReassignTarget(null)}>Cancel</Button>
            <Button
              onClick={submitReassign}
              disabled={newEvaluator.trim().length < 8 || reassignReason.trim().length < 3 || reassign.isPending}
            >Reassign</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Cancel dialog */}
      <Dialog open={Boolean(cancelTarget)} onOpenChange={(o) => { if (!o) setCancelTarget(null) }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Cancel assignment</DialogTitle>
            <DialogDescription>This withdraws the allocation. It cannot be undone.</DialogDescription>
          </DialogHeader>
          <div>
            <label className="text-xs text-gray-500">Reason</label>
            <Input value={cancelReason} onChange={(e) => setCancelReason(e.target.value)}
              placeholder="Why cancel?" className="mt-1" />
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setCancelTarget(null)}>Back</Button>
            <Button variant="destructive" onClick={submitCancel}
              disabled={cancelReason.trim().length < 3 || cancel.isPending}>
              Cancel assignment
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
