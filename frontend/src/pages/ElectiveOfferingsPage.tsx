import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ListChecks, CheckCircle2, XCircle, Send, Rocket } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select, SelectTrigger, SelectValue, SelectContent, SelectItem,
} from '@/components/ui/select'
import { useAuth } from '@/lib/auth'
import { getErrorMessage } from '@/lib/api'
import { academicsApi } from '@/lib/api/academics'
import { listPrograms, listCourses } from '@/lib/api/programs'
import {
  listElectiveOfferings,
  createElectiveOffering,
  proposeElective,
  getMyProposedElectives,
  getPendingElectiveApprovals,
  approveElective,
  rejectElective,
  getApprovedElectives,
  publishElective,
  type ElectiveOffering,
} from '@/lib/api/electives'

function SkeletonRow() {
  return (
    <div className="px-5 py-4 animate-pulse">
      <div className="h-4 w-48 rounded bg-gray-200" />
      <div className="mt-1.5 h-3 w-28 rounded bg-gray-100" />
    </div>
  )
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="text-center py-12 rounded-xl border border-dashed border-gray-200">
      <ListChecks className="h-8 w-8 mx-auto mb-2 text-gray-200" />
      <p className="text-sm text-gray-400">{message}</p>
    </div>
  )
}

const STATUS_COLORS: Record<string, string> = {
  PROPOSED: 'bg-amber-50 text-amber-700',
  DEAN_APPROVED: 'bg-blue-50 text-blue-700',
  REJECTED: 'bg-red-50 text-red-700',
  OPEN: 'bg-green-50 text-green-700',
  CLOSED: 'bg-gray-100 text-gray-500',
}

function StatusPill({ status }: { status: string }) {
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_COLORS[status] ?? 'bg-gray-100 text-gray-500'}`}>
      {status.replace('_', ' ')}
    </span>
  )
}

function OfferingRow({ offering, children }: { offering: ElectiveOffering; children?: React.ReactNode }) {
  return (
    <div className="px-5 py-4 flex items-center justify-between gap-4">
      <div className="min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-semibold text-gray-800">{offering.course_title}</span>
          <span className="text-xs text-gray-400">{offering.course_code}</span>
          <StatusPill status={offering.status} />
        </div>
        <div className="text-xs text-gray-400 mt-1">
          {offering.credits} credits · {offering.seats_taken}/{offering.max_seats} seats
          {offering.faculty_name && ` · ${offering.faculty_name}`}
        </div>
        {offering.rejection_reason && (
          <div className="text-xs text-red-600 mt-1">Rejected: {offering.rejection_reason}</div>
        )}
      </div>
      {children && <div className="flex items-center gap-2 shrink-0">{children}</div>}
    </div>
  )
}

// ---------------------------------------------------------------------------
// FACULTY — propose new electives + track own proposals
// ---------------------------------------------------------------------------

function ProposeElectiveForm() {
  const qc = useQueryClient()
  const [programId, setProgramId] = useState('')
  const [courseId, setCourseId] = useState('')
  const [semesterId, setSemesterId] = useState('')
  const [maxSeats, setMaxSeats] = useState('30')
  const [error, setError] = useState<string | null>(null)

  const programsQ = useQuery({
    queryKey: ['programs-for-elective-picker'],
    queryFn: () => listPrograms({ page_size: 100 }),
  })
  const coursesQ = useQuery({
    queryKey: ['courses-for-elective-picker', programId],
    queryFn: () => listCourses(programId),
    enabled: !!programId,
  })
  const semestersQ = useQuery({
    queryKey: ['semesters-for-elective-picker'],
    queryFn: () => academicsApi.listSemesters(undefined, true),
  })

  const electiveCourses = (coursesQ.data ?? []).filter((c) => c.is_elective)

  const proposeMut = useMutation({
    mutationFn: () =>
      proposeElective({
        course_id: courseId,
        semester_id: semesterId,
        max_seats: Number(maxSeats),
      }),
    onSuccess: () => {
      setError(null)
      setProgramId(''); setCourseId(''); setSemesterId(''); setMaxSeats('30')
      qc.invalidateQueries({ queryKey: ['my-proposed-electives'] })
    },
    onError: (e) => setError(getErrorMessage(e)),
  })

  const canSubmit = !!courseId && !!semesterId && Number(maxSeats) > 0

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 space-y-3">
      <h3 className="text-sm font-semibold text-gray-700">Propose New Elective</h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Select value={programId} onValueChange={(v) => { setProgramId(v); setCourseId('') }}>
          <SelectTrigger><SelectValue placeholder="Select program" /></SelectTrigger>
          <SelectContent>
            {(programsQ.data?.items ?? []).map((p) => (
              <SelectItem key={p.id} value={p.id}>{p.title}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={courseId} onValueChange={setCourseId} disabled={!programId}>
          <SelectTrigger><SelectValue placeholder={programId ? 'Select elective course' : 'Pick a program first'} /></SelectTrigger>
          <SelectContent>
            {electiveCourses.length === 0 ? (
              <div className="px-2 py-3 text-xs text-gray-400">No elective-tagged courses in this program.</div>
            ) : (
              electiveCourses.map((c) => (
                <SelectItem key={c.id} value={c.id}>{c.title} ({c.code})</SelectItem>
              ))
            )}
          </SelectContent>
        </Select>

        <Select value={semesterId} onValueChange={setSemesterId}>
          <SelectTrigger><SelectValue placeholder="Select semester" /></SelectTrigger>
          <SelectContent>
            {(semestersQ.data ?? []).map((s) => (
              <SelectItem key={s.id} value={s.id}>{s.label ?? `Semester ${s.number}`}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Input
          type="number"
          min={1}
          value={maxSeats}
          onChange={(e) => setMaxSeats(e.target.value)}
          placeholder="Max seats"
        />
      </div>

      {error && <div className="text-xs text-red-600">{error}</div>}

      <Button size="sm" disabled={!canSubmit || proposeMut.isPending} onClick={() => proposeMut.mutate()}>
        <Send className="h-3.5 w-3.5 mr-1.5" />
        {proposeMut.isPending ? 'Submitting…' : 'Submit Proposal'}
      </Button>
    </div>
  )
}

function MyProposalsList() {
  const { data, isLoading } = useQuery({
    queryKey: ['my-proposed-electives'],
    queryFn: getMyProposedElectives,
  })
  const items = data ?? []

  if (isLoading) return <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white">{[1, 2].map((n) => <SkeletonRow key={n} />)}</div>
  if (items.length === 0) return <EmptyState message="You haven't proposed any electives yet." />

  return (
    <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
      {items.map((o) => <OfferingRow key={o.id} offering={o} />)}
    </div>
  )
}

// ---------------------------------------------------------------------------
// DEAN — approve / reject pending proposals
// ---------------------------------------------------------------------------

function PendingApprovalsList() {
  const qc = useQueryClient()
  const [rejectingId, setRejectingId] = useState<string | null>(null)
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['pending-elective-approvals'],
    queryFn: getPendingElectiveApprovals,
  })

  const approveMut = useMutation({
    mutationFn: (id: string) => approveElective(id),
    onSuccess: () => {
      setError(null)
      qc.invalidateQueries({ queryKey: ['pending-elective-approvals'] })
    },
    onError: (e) => setError(getErrorMessage(e)),
  })
  const rejectMut = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) => rejectElective(id, reason),
    onSuccess: () => {
      setError(null)
      setRejectingId(null); setReason('')
      qc.invalidateQueries({ queryKey: ['pending-elective-approvals'] })
    },
    onError: (e) => setError(getErrorMessage(e)),
  })

  const items = data ?? []

  if (isLoading) return <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white">{[1, 2].map((n) => <SkeletonRow key={n} />)}</div>
  if (items.length === 0) return <EmptyState message="No elective proposals pending your review." />

  return (
    <div className="space-y-2">
      {error && <div className="text-xs text-red-600">{error}</div>}
      <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
      {items.map((o) => (
        <div key={o.id}>
          <OfferingRow offering={o}>
            <Button size="sm" variant="outline" disabled={approveMut.isPending} onClick={() => approveMut.mutate(o.id)}>
              <CheckCircle2 className="h-3.5 w-3.5 mr-1.5" /> Approve
            </Button>
            <Button size="sm" variant="outline" onClick={() => setRejectingId(rejectingId === o.id ? null : o.id)}>
              <XCircle className="h-3.5 w-3.5 mr-1.5" /> Reject
            </Button>
          </OfferingRow>
          {rejectingId === o.id && (
            <div className="px-5 pb-4 flex items-center gap-2">
              <Input
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Reason for rejection"
                className="flex-1"
              />
              <Button
                size="sm"
                variant="destructive"
                disabled={!reason.trim() || rejectMut.isPending}
                onClick={() => rejectMut.mutate({ id: o.id, reason })}
              >
                Confirm Reject
              </Button>
            </div>
          )}
        </div>
      ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// DEAN — publish dean-approved offerings + direct-create shortcut
// (Ownership correction: Dean owns the full elective lifecycle end-to-end —
// Admin no longer creates, approves, or publishes electives.)
// ---------------------------------------------------------------------------

function ApprovedReadyToPublishList() {
  const qc = useQueryClient()
  const [error, setError] = useState<string | null>(null)
  const { data, isLoading } = useQuery({
    queryKey: ['approved-electives'],
    queryFn: getApprovedElectives,
  })
  const publishMut = useMutation({
    mutationFn: (id: string) => publishElective(id),
    onSuccess: () => {
      setError(null)
      qc.invalidateQueries({ queryKey: ['approved-electives'] })
    },
    onError: (e) => setError(getErrorMessage(e)),
  })

  const items = data ?? []

  if (isLoading) return <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white">{[1, 2].map((n) => <SkeletonRow key={n} />)}</div>
  if (items.length === 0) return <EmptyState message="No dean-approved electives waiting to publish." />

  return (
    <div className="space-y-2">
      {error && <div className="text-xs text-red-600">{error}</div>}
      <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
        {items.map((o) => (
          <OfferingRow key={o.id} offering={o}>
            <Button size="sm" disabled={publishMut.isPending} onClick={() => publishMut.mutate(o.id)}>
              <Rocket className="h-3.5 w-3.5 mr-1.5" /> Publish
            </Button>
          </OfferingRow>
        ))}
      </div>
    </div>
  )
}

function DirectCreateForm() {
  const qc = useQueryClient()
  const [programId, setProgramId] = useState('')
  const [courseId, setCourseId] = useState('')
  const [semesterId, setSemesterId] = useState('')
  const [maxSeats, setMaxSeats] = useState('30')
  const [error, setError] = useState<string | null>(null)

  const programsQ = useQuery({ queryKey: ['programs-for-elective-picker'], queryFn: () => listPrograms({ page_size: 100 }) })
  const coursesQ = useQuery({
    queryKey: ['courses-for-elective-picker', programId],
    queryFn: () => listCourses(programId),
    enabled: !!programId,
  })
  const semestersQ = useQuery({ queryKey: ['semesters-for-elective-picker'], queryFn: () => academicsApi.listSemesters(undefined, true) })
  const electiveCourses = (coursesQ.data ?? []).filter((c) => c.is_elective)

  const createMut = useMutation({
    mutationFn: () => createElectiveOffering({ course_id: courseId, semester_id: semesterId, max_seats: Number(maxSeats) }),
    onSuccess: () => {
      setError(null)
      setProgramId(''); setCourseId(''); setSemesterId(''); setMaxSeats('30')
      qc.invalidateQueries({ queryKey: ['all-elective-offerings'] })
    },
    onError: (e) => setError(getErrorMessage(e)),
  })

  const canSubmit = !!courseId && !!semesterId && Number(maxSeats) > 0

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 space-y-3">
      <h3 className="text-sm font-semibold text-gray-700">Create &amp; Publish Directly</h3>
      <p className="text-xs text-gray-400">Skips the propose/approve workflow — goes straight to OPEN.</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Select value={programId} onValueChange={(v) => { setProgramId(v); setCourseId('') }}>
          <SelectTrigger><SelectValue placeholder="Select program" /></SelectTrigger>
          <SelectContent>
            {(programsQ.data?.items ?? []).map((p) => <SelectItem key={p.id} value={p.id}>{p.title}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={courseId} onValueChange={setCourseId} disabled={!programId}>
          <SelectTrigger><SelectValue placeholder={programId ? 'Select elective course' : 'Pick a program first'} /></SelectTrigger>
          <SelectContent>
            {electiveCourses.map((c) => <SelectItem key={c.id} value={c.id}>{c.title} ({c.code})</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={semesterId} onValueChange={setSemesterId}>
          <SelectTrigger><SelectValue placeholder="Select semester" /></SelectTrigger>
          <SelectContent>
            {(semestersQ.data ?? []).map((s) => <SelectItem key={s.id} value={s.id}>{s.label ?? `Semester ${s.number}`}</SelectItem>)}
          </SelectContent>
        </Select>
        <Input type="number" min={1} value={maxSeats} onChange={(e) => setMaxSeats(e.target.value)} placeholder="Max seats" />
      </div>
      {error && <div className="text-xs text-red-600">{error}</div>}
      <Button size="sm" variant="outline" disabled={!canSubmit || createMut.isPending} onClick={() => createMut.mutate()}>
        {createMut.isPending ? 'Creating…' : 'Create & Publish'}
      </Button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// All roles — read-only context list
// ---------------------------------------------------------------------------

function AllOfferingsList() {
  const semestersQ = useQuery({ queryKey: ['semesters-for-elective-picker'], queryFn: () => academicsApi.listSemesters(undefined, true) })
  const activeSemesterId = semestersQ.data?.find((s) => s.is_active)?.id ?? semestersQ.data?.[0]?.id

  const { data, isLoading } = useQuery({
    queryKey: ['all-elective-offerings', activeSemesterId],
    queryFn: () => listElectiveOfferings(activeSemesterId as string),
    enabled: !!activeSemesterId,
  })
  const items = data ?? []

  if (isLoading) return <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white">{[1, 2].map((n) => <SkeletonRow key={n} />)}</div>
  if (items.length === 0) return <EmptyState message="No elective offerings for the current semester yet." />

  return (
    <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
      {items.map((o) => <OfferingRow key={o.id} offering={o} />)}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Root page — role-gated sections, one shared destination
// ---------------------------------------------------------------------------

export default function ElectiveOfferingsPage() {
  const { user } = useAuth()
  const role = user?.role

  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Elective Offerings</h1>
        <p className="text-sm text-gray-400 mt-0.5">
          Faculty propose → Dean approves and publishes. Dean owns the elective lifecycle end-to-end.
        </p>
      </div>

      {role === 'FACULTY' && (
        <section className="space-y-3">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-400">My Proposals</h2>
          <ProposeElectiveForm />
          <MyProposalsList />
        </section>
      )}

      {role === 'DEAN' && (
        <>
          <section className="space-y-3">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-400">Pending Approvals</h2>
            <PendingApprovalsList />
          </section>

          <section className="space-y-3">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-400">Approved — Ready to Publish</h2>
            <ApprovedReadyToPublishList />
            <DirectCreateForm />
          </section>
        </>
      )}

      <section className="space-y-3">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-400">All Offerings (current semester)</h2>
        <AllOfferingsList />
      </section>
    </div>
  )
}
