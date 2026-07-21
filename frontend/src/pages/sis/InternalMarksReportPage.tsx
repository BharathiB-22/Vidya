import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Lock, Unlock, Info, CheckCircle2, XCircle, AlertTriangle, BookMarked } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Textarea } from '@/components/ui/textarea'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { sisApi, MarksComponent, SectionReadinessOut } from '@/lib/api/sis'
import { academicsApi } from '@/lib/api/academics'
import { listAllCourses } from '@/lib/api/programs'

const STATUS_COLORS: Record<string, string> = {
  DRAFT:     'bg-yellow-100 text-yellow-800 border-yellow-200',
  PUBLISHED: 'bg-green-100  text-green-800  border-green-200',
  LOCKED:    'bg-gray-100   text-gray-700   border-gray-300',
}

export default function InternalMarksReportPage() {
  const qc = useQueryClient()

  // Friendly academic selectors — the user never types a UUID. Program → Batch →
  // Semester → Section resolves to the sectionId the report API needs; the
  // optional Course dropdown resolves to courseId.
  const [programId, setProgramId]   = useState('')
  const [batchId, setBatchId]       = useState('')
  const [semesterId, setSemesterId] = useState('')
  const [sectionId, setSectionId]   = useState('')
  const [courseId, setCourseId]     = useState('')
  const [submitted, setSubmitted]   = useState('')

  const [lockTarget,   setLockTarget]   = useState<MarksComponent | null>(null)
  const [reopenTarget, setReopenTarget] = useState<MarksComponent | null>(null)
  const [reopenReason, setReopenReason] = useState('')

  const { data: report, isLoading: rLoading } = useQuery({
    queryKey: ['marks-section-report', submitted, courseId],
    queryFn:  () => sisApi.getSectionMarksReport(submitted, courseId || undefined),
    enabled:  !!submitted,
  })
  const { data: readiness, isLoading: readLoading } = useQuery({
    queryKey: ['marks-readiness', submitted],
    queryFn:  () => sisApi.getSectionReadiness(submitted),
    enabled:  !!submitted,
  })

  const lockMutation = useMutation({
    mutationFn: (id: string) => sisApi.lockMarksComponent(id),
    onSuccess:  () => { qc.invalidateQueries({ queryKey: ['marks-section-report'] }); setLockTarget(null) },
  })
  const reopenMutation = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) => sisApi.reopenMarksComponent(id, reason),
    onSuccess:  () => { qc.invalidateQueries({ queryKey: ['marks-section-report'] }); setReopenTarget(null); setReopenReason('') },
  })

  // Cascading academic dropdowns (reuse existing academic list APIs).
  const { data: programs = [] } = useQuery({
    queryKey: ['imr-programs'], queryFn: () => academicsApi.listPrograms(),
  })
  const { data: batches = [] } = useQuery({
    queryKey: ['imr-batches', programId], queryFn: () => academicsApi.listBatches(programId || undefined),
    enabled: !!programId,
  })
  const { data: semesters = [] } = useQuery({
    queryKey: ['imr-semesters', batchId], queryFn: () => academicsApi.listSemesters(batchId || undefined),
    enabled: !!batchId,
  })
  const { data: sections = [] } = useQuery({
    queryKey: ['imr-sections', semesterId], queryFn: () => academicsApi.listSections(semesterId || undefined),
    enabled: !!semesterId,
  })
  const { data: courses = [] } = useQuery({
    queryKey: ['imr-courses'], queryFn: () => listAllCourses(),
  })

  return (
    <PageShell>
      <PageHeader icon={BookMarked} title="Internal Marks Report" subtitle="Review, lock, and reopen marks by section." />

      <div className="flex gap-2 items-start rounded-md border border-blue-200 bg-blue-50 p-3 text-sm text-blue-800 mb-4">
        <Info className="h-4 w-4 mt-0.5 shrink-0" />
        <span>
          <strong>Lock</strong> finalizes marks for eligibility processing. You may reopen with a reason.
          Locking is advisory — no autonomous grades are computed.
        </span>
      </div>

      {/* Filters — friendly academic selectors (no UUIDs) */}
      <div className="flex flex-wrap gap-3 items-end mb-6">
        <div>
          <p className="text-xs font-medium mb-1 text-gray-700">Program</p>
          <Select value={programId} onValueChange={v => { setProgramId(v); setBatchId(''); setSemesterId(''); setSectionId('') }}>
            <SelectTrigger className="w-[190px]"><SelectValue placeholder="Select program" /></SelectTrigger>
            <SelectContent>
              {programs.map(p => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div>
          <p className="text-xs font-medium mb-1 text-gray-700">Batch</p>
          <Select value={batchId} onValueChange={v => { setBatchId(v); setSemesterId(''); setSectionId('') }} disabled={!programId}>
            <SelectTrigger className="w-[160px]"><SelectValue placeholder="Select batch" /></SelectTrigger>
            <SelectContent>
              {batches.map(b => <SelectItem key={b.id} value={b.id}>{b.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div>
          <p className="text-xs font-medium mb-1 text-gray-700">Semester</p>
          <Select value={semesterId} onValueChange={v => { setSemesterId(v); setSectionId('') }} disabled={!batchId}>
            <SelectTrigger className="w-[160px]"><SelectValue placeholder="Select semester" /></SelectTrigger>
            <SelectContent>
              {semesters.map(s => <SelectItem key={s.id} value={s.id}>Sem {s.number}{s.label ? ` — ${s.label}` : ''}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div>
          <p className="text-xs font-medium mb-1 text-gray-700">Section</p>
          <Select value={sectionId} onValueChange={setSectionId} disabled={!semesterId}>
            <SelectTrigger className="w-[150px]"><SelectValue placeholder="Select section" /></SelectTrigger>
            <SelectContent>
              {sections.map(s => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div>
          <p className="text-xs font-medium mb-1 text-gray-700">Course (optional)</p>
          <Select value={courseId || 'ALL'} onValueChange={v => setCourseId(v === 'ALL' ? '' : v)}>
            <SelectTrigger className="w-[220px]"><SelectValue placeholder="All courses" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="ALL">All courses</SelectItem>
              {courses.map(c => <SelectItem key={c.id} value={c.id}>{c.code ? `${c.code} — ${c.title}` : c.title}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <Button onClick={() => setSubmitted(sectionId)} disabled={!sectionId}>Load Report</Button>
      </div>

      {(rLoading || readLoading) && <p className="text-muted-foreground">Loading…</p>}

      {report && (
        <Tabs defaultValue="components">
          <TabsList>
            <TabsTrigger value="components">Components</TabsTrigger>
            <TabsTrigger value="students">Student Marks</TabsTrigger>
            <TabsTrigger value="readiness">Readiness</TabsTrigger>
          </TabsList>

          <TabsContent value="components" className="mt-4">
            <p className="text-sm text-muted-foreground mb-3">
              {report.section_name} — {report.course_code} {report.course_title}
            </p>
            <div className="rounded-md border overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-muted/40 text-xs uppercase text-muted-foreground">
                  <tr>
                    <th className="px-4 py-2 text-left">Component</th>
                    <th className="px-4 py-2 text-left">Type</th>
                    <th className="px-4 py-2 text-right">Max</th>
                    <th className="px-4 py-2 text-right">Fill</th>
                    <th className="px-4 py-2 text-center">Status</th>
                    <th className="px-4 py-2 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {report.components.map((c: MarksComponent) => (
                    <tr key={c.id} className="hover:bg-muted/20">
                      <td className="px-4 py-2 font-medium">{c.name}</td>
                      <td className="px-4 py-2 text-muted-foreground">{c.component_type}</td>
                      <td className="px-4 py-2 text-right">{c.max_marks}</td>
                      <td className="px-4 py-2 text-right">
                        {c.filled_count}/{c.entries_count}
                        {c.filled_count < c.entries_count && (
                          <AlertTriangle className="inline ml-1 h-3 w-3 text-amber-500" />
                        )}
                      </td>
                      <td className="px-4 py-2 text-center">
                        <Badge variant="outline" className={`text-xs ${STATUS_COLORS[c.status]}`}>{c.status}</Badge>
                      </td>
                      <td className="px-4 py-2 text-right">
                        {c.status === 'PUBLISHED' && (
                          <Button size="sm" variant="outline" onClick={() => setLockTarget(c)}>
                            <Lock className="h-3 w-3 mr-1" />Lock
                          </Button>
                        )}
                        {c.status === 'LOCKED' && (
                          <Button size="sm" variant="ghost" onClick={() => setReopenTarget(c)}>
                            <Unlock className="h-3 w-3 mr-1" />Reopen
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                  {report.components.length === 0 && (
                    <tr><td colSpan={6} className="px-4 py-6 text-center text-muted-foreground">No components found.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </TabsContent>

          <TabsContent value="students" className="mt-4">
            <div className="rounded-md border overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-muted/40 text-xs uppercase text-muted-foreground">
                  <tr>
                    <th className="px-4 py-2 text-left">USN</th>
                    <th className="px-4 py-2 text-left">Name</th>
                    <th className="px-4 py-2 text-right">Total</th>
                    <th className="px-4 py-2 text-right">Max</th>
                    <th className="px-4 py-2 text-right">Fill %</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {report.students.map((s: any) => (
                    <tr key={s.student_id} className="hover:bg-muted/20">
                      <td className="px-4 py-2 font-mono text-xs">{s.usn ?? '—'}</td>
                      <td className="px-4 py-2">{s.student_name}</td>
                      <td className="px-4 py-2 text-right">{s.total_marks !== null ? Number(s.total_marks).toFixed(1) : '—'}</td>
                      <td className="px-4 py-2 text-right">{s.total_max !== null ? Number(s.total_max).toFixed(1) : '—'}</td>
                      <td className="px-4 py-2 text-right">{s.fill_pct !== null ? `${s.fill_pct}%` : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </TabsContent>

          <TabsContent value="readiness" className="mt-4">
            {readiness && <ReadinessSummary data={readiness} />}
          </TabsContent>
        </Tabs>
      )}

      {/* Lock confirm */}
      <Dialog open={!!lockTarget} onOpenChange={() => setLockTarget(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Lock Component</DialogTitle></DialogHeader>
          <div className="flex gap-2 items-start rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
            <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
            Locking <strong>{lockTarget?.name}</strong> prevents faculty edits. You can reopen with a reason.
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setLockTarget(null)}>Cancel</Button>
            <Button onClick={() => lockTarget && lockMutation.mutate(lockTarget.id)} disabled={lockMutation.isPending}>
              {lockMutation.isPending ? 'Locking…' : 'Lock Marks'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Reopen */}
      <Dialog open={!!reopenTarget} onOpenChange={() => { setReopenTarget(null); setReopenReason('') }}>
        <DialogContent>
          <DialogHeader><DialogTitle>Reopen Component</DialogTitle></DialogHeader>
          <p className="text-sm text-muted-foreground">Reopening <strong>{reopenTarget?.name}</strong> allows faculty to edit marks again.</p>
          <Textarea rows={3} value={reopenReason} onChange={e => setReopenReason(e.target.value)}
            placeholder="e.g. Faculty reported data entry error in 3 student records" />
          <DialogFooter>
            <Button variant="outline" onClick={() => { setReopenTarget(null); setReopenReason('') }}>Cancel</Button>
            <Button
              onClick={() => reopenTarget && reopenMutation.mutate({ id: reopenTarget.id, reason: reopenReason })}
              disabled={!reopenReason.trim() || reopenMutation.isPending}>
              {reopenMutation.isPending ? 'Reopening…' : 'Reopen'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageShell>
  )
}

function ReadinessSummary({ data }: { data: SectionReadinessOut }) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: 'Attendance Ready', value: data.attendance_ready_count },
          { label: 'Marks Ready',      value: data.internal_marks_ready_count },
          { label: 'Fully Ready',      value: data.fully_ready_count, green: true },
        ].map(item => (
          <div key={item.label} className="rounded-md border p-4">
            <p className="text-xs text-muted-foreground">{item.label}</p>
            <p className={`text-2xl font-bold ${item.green ? 'text-green-700' : ''}`}>
              {item.value}<span className="text-sm font-normal text-muted-foreground">/{data.total_students}</span>
            </p>
          </div>
        ))}
      </div>
      <div className="flex gap-2 items-start rounded-md border border-blue-200 bg-blue-50 p-3 text-sm text-blue-800">
        <Info className="h-4 w-4 mt-0.5 shrink-0" />
        Advisory only. Readiness indicators do not block hall-ticket issuance.
      </div>
      <div className="rounded-md border overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-muted/40 text-xs uppercase text-muted-foreground">
            <tr>
              <th className="px-4 py-2 text-left">USN</th>
              <th className="px-4 py-2 text-left">Name</th>
              <th className="px-4 py-2 text-center">Att %</th>
              <th className="px-4 py-2 text-center">Att ✓</th>
              <th className="px-4 py-2 text-center">Marks %</th>
              <th className="px-4 py-2 text-center">Marks ✓</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {data.students.map(s => (
              <tr key={s.student_id} className="hover:bg-muted/20">
                <td className="px-4 py-2 font-mono text-xs">{s.usn ?? '—'}</td>
                <td className="px-4 py-2">{s.student_name}</td>
                <td className="px-4 py-2 text-center">{s.attendance_pct !== null ? `${s.attendance_pct.toFixed(1)}%` : '—'}</td>
                <td className="px-4 py-2 text-center">
                  {s.attendance_ready
                    ? <CheckCircle2 className="h-4 w-4 text-green-600 mx-auto" />
                    : <XCircle className="h-4 w-4 text-red-400 mx-auto" />}
                </td>
                <td className="px-4 py-2 text-center">{s.marks_fill_pct !== null ? `${s.marks_fill_pct}%` : '—'}</td>
                <td className="px-4 py-2 text-center">
                  {s.internal_marks_ready
                    ? <CheckCircle2 className="h-4 w-4 text-green-600 mx-auto" />
                    : <XCircle className="h-4 w-4 text-red-400 mx-auto" />}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
