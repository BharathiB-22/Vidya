import { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ListChecks, Users2, PlusCircle, Layers, GraduationCap, BarChart3, Lock, Unlock,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select, SelectTrigger, SelectValue, SelectContent, SelectItem,
} from '@/components/ui/select'
import { getErrorMessage } from '@/lib/api'
import { academicsApi } from '@/lib/api/academics'
import { assignmentsApi } from '@/lib/api/assignments'
import {
  listEligibleElectiveBaskets,
  createElectiveOffering,
  assignElectiveFaculty,
  updateElectiveOffering,
  getDeanElectiveDashboard,
  type ElectiveOffering,
  type EligibleElectiveBasket,
} from '@/lib/api/electives'

type FacultyUser = { id: string; full_name: string; email: string; role: string }

const UNASSIGNED = '__unassigned__'

function StatCard({ label, value, icon: Icon }: { label: string; value: number | string; icon: typeof Users2 }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 flex items-center gap-3">
      <div className="h-9 w-9 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0">
        <Icon className="h-5 w-5" />
      </div>
      <div>
        <div className="text-xl font-bold text-gray-900 leading-none">{value}</div>
        <div className="text-xs text-gray-500 mt-1">{label}</div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Faculty picker — one dropdown, reused in create form + per-offering rows
// ---------------------------------------------------------------------------

function FacultyPicker({
  faculty, value, onChange, disabled,
}: {
  faculty: FacultyUser[]
  value: string
  onChange: (facultyUserId: string) => void
  disabled?: boolean
}) {
  return (
    <Select value={value || UNASSIGNED} onValueChange={(v) => onChange(v === UNASSIGNED ? '' : v)} disabled={disabled}>
      <SelectTrigger className="h-8 w-52 text-xs">
        <SelectValue placeholder="Assign faculty" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={UNASSIGNED}>— Unassigned —</SelectItem>
        {faculty.map((f) => (
          <SelectItem key={f.id} value={f.id}>{f.full_name}</SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

// ---------------------------------------------------------------------------
// Create offering
// ---------------------------------------------------------------------------

function CreateOfferingForm({ semesterId, faculty }: { semesterId: string; faculty: FacultyUser[] }) {
  const qc = useQueryClient()
  const [basketId, setBasketId] = useState('')
  const [maxSeats, setMaxSeats] = useState('30')
  const [facultyByCourse, setFacultyByCourse] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)

  const basketsQ = useQuery({
    queryKey: ['eligible-elective-baskets', semesterId],
    queryFn: () => listEligibleElectiveBaskets(semesterId),
    enabled: !!semesterId,
  })

  const baskets = basketsQ.data ?? []
  const selectedBasket: EligibleElectiveBasket | undefined = baskets.find((b) => b.basket_id === basketId)

  const createMut = useMutation({
    mutationFn: () =>
      createElectiveOffering({
        basket_id: basketId,
        semester_id: semesterId,
        max_seats: Number(maxSeats),
        faculty_assignments: Object.entries(facultyByCourse)
          .filter(([, f]) => !!f)
          .map(([course_id, faculty_user_id]) => ({ course_id, faculty_user_id })),
      }),
    onSuccess: () => {
      setError(null); setBasketId(''); setMaxSeats('30'); setFacultyByCourse({})
      qc.invalidateQueries({ queryKey: ['dean-elective-dashboard'] })
      qc.invalidateQueries({ queryKey: ['eligible-elective-baskets'] })
    },
    onError: (e) => setError(getErrorMessage(e)),
  })

  const canSubmit = !!basketId && Number(maxSeats) > 0 && !selectedBasket?.already_offered

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 space-y-4">
      <div className="flex items-center gap-2">
        <PlusCircle className="h-4 w-4 text-indigo-600" />
        <h3 className="text-sm font-semibold text-gray-900">Create Elective Offering</h3>
      </div>
      <p className="text-xs text-gray-500">
        Pick an elective basket (a placeholder like “Elective 1” with its available courses), set the
        per-course seat limit, and assign the faculty who will teach each course.
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-[1fr_10rem] gap-3">
        <Select value={basketId} onValueChange={setBasketId}>
          <SelectTrigger><SelectValue placeholder={baskets.length ? 'Select elective basket' : 'No baskets published for this semester'} /></SelectTrigger>
          <SelectContent>
            {baskets.map((b) => (
              <SelectItem key={b.basket_id} value={b.basket_id} disabled={b.already_offered}>
                {b.name} ({b.courses.length} courses){b.already_offered ? ' — already offered' : ''}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Input
          type="number"
          min={1}
          value={maxSeats}
          onChange={(e) => setMaxSeats(e.target.value)}
          placeholder="Seats / course"
        />
      </div>

      {selectedBasket && (
        <div className="rounded-lg border border-gray-100 bg-gray-50/60 divide-y divide-gray-100">
          {selectedBasket.courses.map((c) => (
            <div key={c.course_id} className="flex items-center justify-between gap-3 px-3 py-2.5">
              <div className="min-w-0">
                <span className="text-sm font-medium text-gray-900">{c.title}</span>
                <span className="text-xs text-gray-500 ml-2">{c.code} · {c.credits} cr</span>
              </div>
              <FacultyPicker
                faculty={faculty}
                value={facultyByCourse[c.course_id] ?? c.faculty_user_id ?? ''}
                onChange={(f) => setFacultyByCourse((p) => ({ ...p, [c.course_id]: f }))}
              />
            </div>
          ))}
        </div>
      )}

      {error && <div className="text-xs text-red-600">{error}</div>}

      <Button size="sm" disabled={!canSubmit || createMut.isPending} onClick={() => createMut.mutate()}>
        {createMut.isPending ? 'Creating…' : 'Create Offering'}
      </Button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Existing offering card — per-course demand + faculty reassignment + open/close
// ---------------------------------------------------------------------------

function OfferingCard({ offering, faculty }: { offering: ElectiveOffering; faculty: FacultyUser[] }) {
  const qc = useQueryClient()
  const [error, setError] = useState<string | null>(null)

  const invalidate = () => qc.invalidateQueries({ queryKey: ['dean-elective-dashboard'] })

  const assignMut = useMutation({
    mutationFn: ({ courseId, facultyUserId }: { courseId: string; facultyUserId: string }) =>
      assignElectiveFaculty(offering.id, courseId, facultyUserId),
    onSuccess: () => { setError(null); invalidate() },
    onError: (e) => setError(getErrorMessage(e)),
  })

  const statusMut = useMutation({
    mutationFn: (status: 'OPEN' | 'CLOSED') => updateElectiveOffering(offering.id, { status }),
    onSuccess: () => { setError(null); invalidate() },
    onError: (e) => setError(getErrorMessage(e)),
  })

  const totalRegistered = offering.courses.reduce((s, c) => s + c.seats_taken, 0)
  const isClosed = offering.status === 'CLOSED'

  return (
    <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
      <div className="flex items-center justify-between gap-4 px-4 py-3 bg-gray-50 border-b border-gray-100">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <Layers className="h-4 w-4 text-indigo-500" />
            <span className="text-sm font-semibold text-gray-900">{offering.basket_name}</span>
            <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${isClosed ? 'bg-gray-200 text-gray-600' : 'bg-green-50 text-green-700'}`}>
              {offering.status}
            </span>
          </div>
          <div className="text-xs text-gray-500 mt-1">
            {offering.max_seats} seats/course · {totalRegistered} registered
          </div>
        </div>
        <Button
          size="sm"
          variant="outline"
          disabled={statusMut.isPending}
          onClick={() => statusMut.mutate(isClosed ? 'OPEN' : 'CLOSED')}
        >
          {isClosed ? <Unlock className="h-3.5 w-3.5 mr-1" /> : <Lock className="h-3.5 w-3.5 mr-1" />}
          {isClosed ? 'Reopen' : 'Close'}
        </Button>
      </div>

      {error && <div className="text-xs text-red-600 px-4 pt-2">{error}</div>}

      <div className="divide-y divide-gray-100">
        {offering.courses.map((c) => {
          const seatsLeft = offering.max_seats - c.seats_taken
          return (
            <div key={c.course_id} className="flex items-center justify-between gap-4 px-4 py-2.5">
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-medium text-gray-900">{c.title}</span>
                  <span className="text-xs text-gray-500">{c.code}</span>
                </div>
                <div className="flex items-center gap-1 text-xs text-gray-600 mt-0.5">
                  <Users2 className="h-3.5 w-3.5" />
                  <span className="font-medium text-gray-900">{c.seats_taken}</span> registered · {seatsLeft} left
                </div>
              </div>
              <FacultyPicker
                faculty={faculty}
                value={c.faculty_user_id ?? ''}
                disabled={assignMut.isPending}
                onChange={(facultyUserId) => {
                  if (facultyUserId && facultyUserId !== c.faculty_user_id) {
                    assignMut.mutate({ courseId: c.course_id, facultyUserId })
                  }
                }}
              />
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function ElectiveOfferingsPage() {
  const [semesterId, setSemesterId] = useState('')

  const semestersQ = useQuery({
    queryKey: ['semesters-for-elective-picker'],
    queryFn: () => academicsApi.listSemesters(undefined, true),
  })
  const semesters = semestersQ.data ?? []
  const activeSemesterId = useMemo(
    () => semesterId || semesters.find((s) => s.is_active)?.id || semesters[0]?.id || '',
    [semesterId, semesters],
  )

  const facultyQ = useQuery({
    queryKey: ['assignable-faculty'],
    queryFn: () => assignmentsApi.listFacultyUsers(),
  })
  const faculty = facultyQ.data ?? []

  const dashboardQ = useQuery({
    queryKey: ['dean-elective-dashboard', activeSemesterId],
    queryFn: () => getDeanElectiveDashboard(activeSemesterId),
    enabled: !!activeSemesterId,
  })
  const dashboard = dashboardQ.data

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Elective Offerings</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Create elective offerings, assign teaching faculty, and track live registration demand.
          </p>
        </div>
        <Select value={activeSemesterId} onValueChange={setSemesterId}>
          <SelectTrigger className="w-56"><SelectValue placeholder="Select semester" /></SelectTrigger>
          <SelectContent>
            {semesters.map((s) => (
              <SelectItem key={s.id} value={s.id}>{s.label ?? `Semester ${s.number}`}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Dashboard */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <StatCard label="Offerings" value={dashboard?.total_offerings ?? 0} icon={ListChecks} />
        <StatCard label="Total registrations" value={dashboard?.total_registrations ?? 0} icon={Users2} />
        <StatCard
          label="Faculty assigned"
          value={
            (dashboard?.offerings ?? []).reduce(
              (s, o) => s + o.courses.filter((c) => c.faculty_user_id).length, 0,
            )
          }
          icon={GraduationCap}
        />
      </div>

      {activeSemesterId && <CreateOfferingForm semesterId={activeSemesterId} faculty={faculty} />}

      {/* Offerings list */}
      <section className="space-y-3">
        <div className="flex items-center gap-2">
          <BarChart3 className="h-4 w-4 text-gray-400" />
          <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-500">
            Offerings & demand
          </h2>
        </div>
        {dashboardQ.isLoading ? (
          <div className="h-24 rounded-xl bg-gray-50 animate-pulse" />
        ) : (dashboard?.offerings ?? []).length === 0 ? (
          <div className="text-center py-12 rounded-xl border border-dashed border-gray-200">
            <ListChecks className="h-8 w-8 mx-auto mb-2 text-gray-200" />
            <p className="text-sm text-gray-500">No elective offerings for this semester yet.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {dashboard!.offerings.map((o) => (
              <OfferingCard key={o.id} offering={o} faculty={faculty} />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
