import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ClipboardList, Plus, ChevronRight, AlertCircle } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { sisApi, ResultDeclarationListOut } from '@/lib/api/sis'

const STATUS_COLORS: Record<string, string> = {
  DRAFT:     'bg-yellow-100 text-yellow-800 border-yellow-200',
  VERIFIED:  'bg-blue-100   text-blue-800   border-blue-200',
  PUBLISHED: 'bg-green-100  text-green-800  border-green-200',
  LOCKED:    'bg-gray-100   text-gray-700   border-gray-300',
}

const TYPE_LABELS: Record<string, string> = {
  REGULAR: 'Regular', SUPPLEMENTARY: 'Supplementary', REVALUATION: 'Revaluation',
}

function CreateDeclarationDialog({
  open, onClose,
}: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient()
  const nav = useNavigate()
  const [examSessionId, setExamSessionId] = useState('')
  const [semesterId, setSemesterId] = useState('')
  const [gradingPolicyId, setGradingPolicyId] = useState('')
  const [declType, setDeclType] = useState('REGULAR')
  const [title, setTitle] = useState('')

  const { data: policies } = useQuery({
    queryKey: ['grading-policies'],
    queryFn: sisApi.listGradingPolicies,
    enabled: open,
  })

  const mut = useMutation({
    mutationFn: () => sisApi.createDeclaration({
      exam_session_id: examSessionId,
      semester_id: semesterId,
      grading_policy_id: gradingPolicyId,
      declaration_type: declType,
      title: title || undefined,
    }),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['result-declarations'] })
      onClose()
      nav(`/sis/results/${data.id}`)
    },
  })

  const resetAndClose = () => {
    setExamSessionId(''); setSemesterId(''); setGradingPolicyId('')
    setDeclType('REGULAR'); setTitle('')
    onClose()
  }

  return (
    <Dialog open={open} onOpenChange={v => !v && resetAndClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>New Result Declaration</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <div>
            <label className="text-xs font-medium">Exam Session ID</label>
            <Input value={examSessionId} onChange={e => setExamSessionId(e.target.value)}
              placeholder="UUID of the exam session" className="mt-1" />
          </div>
          <div>
            <label className="text-xs font-medium">Semester ID</label>
            <Input value={semesterId} onChange={e => setSemesterId(e.target.value)}
              placeholder="UUID of the semester" className="mt-1" />
          </div>
          <div>
            <label className="text-xs font-medium">Grading Policy</label>
            <Select value={gradingPolicyId} onValueChange={setGradingPolicyId}>
              <SelectTrigger className="mt-1">
                <SelectValue placeholder="Select policy" />
              </SelectTrigger>
              <SelectContent>
                {(policies ?? []).map(p => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.name}{p.is_default ? ' (default)' : ''}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <label className="text-xs font-medium">Declaration Type</label>
            <Select value={declType} onValueChange={setDeclType}>
              <SelectTrigger className="mt-1">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="REGULAR">Regular</SelectItem>
                <SelectItem value="SUPPLEMENTARY">Supplementary</SelectItem>
                <SelectItem value="REVALUATION">Revaluation</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <label className="text-xs font-medium">Title (optional)</label>
            <Input value={title} onChange={e => setTitle(e.target.value)}
              placeholder="e.g. Nov / Dec 2025" className="mt-1" />
          </div>
          {mut.isError && (
            <p className="text-sm text-red-600">{String(mut.error)}</p>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={resetAndClose}>Cancel</Button>
          <Button
            disabled={!examSessionId || !semesterId || !gradingPolicyId || mut.isPending}
            onClick={() => mut.mutate()}
          >
            {mut.isPending ? 'Creating…' : 'Create'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default function ResultDeclarationsListPage() {
  const nav = useNavigate()
  const [showCreate, setShowCreate] = useState(false)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['result-declarations'],
    queryFn:  () => sisApi.listDeclarations(),
  })

  if (isLoading) return <div className="p-6 text-muted-foreground">Loading result declarations…</div>
  if (isError)   return <div className="p-6 text-red-600">Failed to load declarations.</div>

  const declarations = data ?? []

  return (
    <PageShell>
      <PageHeader
        icon={ClipboardList}
        title="Result Declarations"
        subtitle="Manage exam result declarations, grading, and publication."
        action={
          <Button size="sm" onClick={() => setShowCreate(true)}>
            <Plus className="h-4 w-4 mr-1" />New Declaration
          </Button>
        }
      />

      {declarations.length === 0 ? (
        <div className="text-center py-16 text-muted-foreground">
          No result declarations yet. Create one to get started.
        </div>
      ) : (
        <div className="rounded-md border overflow-hidden mt-4">
          <table className="w-full text-sm">
            <thead className="bg-muted/20 text-xs uppercase text-muted-foreground">
              <tr>
                <th className="px-4 py-2 text-left">Semester / Year</th>
                <th className="px-4 py-2 text-left">Title</th>
                <th className="px-4 py-2 text-left">Type</th>
                <th className="px-4 py-2 text-left">Policy</th>
                <th className="px-4 py-2 text-center">Status</th>
                <th className="px-4 py-2 text-left">Published</th>
                <th className="px-4 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y">
              {declarations.map((d: ResultDeclarationListOut) => (
                <tr key={d.id}
                  className="hover:bg-muted/10 cursor-pointer"
                  onClick={() => nav(`/sis/results/${d.id}`)}
                >
                  <td className="px-4 py-3">
                    <div className="font-medium">{d.snapshot_semester_name}</div>
                    <div className="text-xs text-muted-foreground">{d.snapshot_academic_year}</div>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{d.title ?? '—'}</td>
                  <td className="px-4 py-3">
                    <Badge variant="outline" className="text-xs">
                      {TYPE_LABELS[d.declaration_type] ?? d.declaration_type}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 text-xs text-muted-foreground">{d.snapshot_grading_policy_name}</td>
                  <td className="px-4 py-3 text-center">
                    <Badge variant="outline" className={`text-xs ${STATUS_COLORS[d.status] ?? ''}`}>
                      {d.status}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 text-xs text-muted-foreground">
                    {d.published_at ? new Date(d.published_at).toLocaleDateString() : '—'}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <ChevronRight className="h-4 w-4 text-muted-foreground inline" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {declarations.some((d: ResultDeclarationListOut) => d.status === 'DRAFT') && (
        <div className="flex gap-2 items-start rounded-md border border-yellow-200 bg-yellow-50 p-3 text-sm text-yellow-800 mt-4">
          <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
          Some declarations are in DRAFT state. Open them to enter external marks and compute results.
        </div>
      )}

      <CreateDeclarationDialog open={showCreate} onClose={() => setShowCreate(false)} />
    </PageShell>
  )
}
