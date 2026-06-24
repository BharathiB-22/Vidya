import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft, UserCheck, BookOpen, Building2, Phone, MapPin, Calendar, Pencil, X, Save,
  Activity, ChevronDown, BadgeCheck, Mail, KeyRound, ShieldCheck, Plus, Minus,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { PageShell } from '@/components/shell/PageShell'
import { PageLoading } from '@/components/shared/PageLoading'
import { addToast } from '@/hooks/useToast'
import { getErrorMessage } from '@/lib/api'
import { sisApi } from '@/lib/api/sis'
import type { FacultyDetailOut, FacultyProfileUpsert, FacultyLifecycleStatusOut } from '@/lib/api/sis'
import { onboardingApi } from '@/lib/api/onboarding'
import type { GrantableRole } from '@/lib/api/onboarding'
import { academicsApi } from '@/lib/api/academics'
import { useAuth } from '@/lib/auth'

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between py-3 gap-4 border-b border-gray-100 last:border-0">
      <span className="text-sm text-gray-500 flex-shrink-0">{label}</span>
      <span className="text-sm text-gray-900 font-medium text-right">{value || '—'}</span>
    </div>
  )
}

function Card({ title, icon: Icon, children }: { title: string; icon: typeof UserCheck; children: React.ReactNode }) {
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

function RoleChip({ role }: { role: string }) {
  const colors: Record<string, string> = {
    PRIMARY: '#6366f1', CO_FACULTY: '#10b981', GUEST: '#f59e0b',
  }
  const c = colors[role] ?? '#64748b'
  return (
    <span
      className="text-xs px-2 py-0.5 rounded"
      style={{ background: `${c}18`, color: c, border: `1px solid ${c}30` }}
    >
      {role.replace('_', ' ')}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Responsibility (grant) chips — GUIDE / EVALUATOR / DEAN badge
// ---------------------------------------------------------------------------

const RESPONSIBILITY_COLORS: Record<string, string> = {
  GUIDE: '#6366f1', EVALUATOR: '#10b981', DEAN: '#ec4899',
}

function ResponsibilityChip({ role }: { role: string }) {
  const c = RESPONSIBILITY_COLORS[role] ?? '#64748b'
  return (
    <span
      className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full"
      style={{ background: `${c}1A`, color: c, border: `1px solid ${c}40` }}
    >
      <ShieldCheck className="h-3 w-3" />
      {role}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Responsibilities card — display + ADMIN/DEAN grant management
// ---------------------------------------------------------------------------

/** Which responsibilities the signed-in actor may assign/remove.
 *  Only GUIDE and EVALUATOR are grantable (P1.9).
 *  BOARD and DEAN are primary roles set on the Users page, never grants. */
function assignableRoles(actorRole: string | undefined): GrantableRole[] {
  if (actorRole === 'ADMIN' || actorRole === 'DEAN') return ['GUIDE', 'EVALUATOR']
  return []
}

function ResponsibilitiesCard({
  facultyUserId,
  responsibilities,
}: {
  facultyUserId: string
  responsibilities: string[]
}) {
  const qc = useQueryClient()
  const { user } = useAuth()
  const manageable = assignableRoles(user?.role)
  const held = new Set(responsibilities)

  const mut = useMutation({
    mutationFn: ({ role, action }: { role: GrantableRole; action: 'grant' | 'revoke' }) =>
      action === 'grant'
        ? onboardingApi.grantFacultyRole(facultyUserId, role)
        : onboardingApi.revokeFacultyRole(facultyUserId, role),
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: ['sis-faculty-detail', facultyUserId] })
      qc.invalidateQueries({ queryKey: ['sis-faculty-directory'] })
      addToast(
        `${vars.role} ${vars.action === 'grant' ? 'assigned' : 'removed'}.`,
        'success',
      )
    },
    onError: (e) => addToast(getErrorMessage(e), 'error'),
  })

  return (
    <Card title="Responsibilities" icon={ShieldCheck}>
      <div className="py-3">
        {responsibilities.length === 0 ? (
          <p className="text-sm text-gray-500">No responsibilities assigned.</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {responsibilities.map(r => <ResponsibilityChip key={r} role={r} />)}
          </div>
        )}
      </div>

      {manageable.length > 0 && (
        <div className="pt-1 space-y-2">
          <p className="text-xs text-gray-500">
            Assign GUIDE or EVALUATOR responsibilities. BOARD accounts are managed from the Users page.
          </p>
          <div className="flex flex-wrap gap-2">
            {manageable.map(role => {
              const has = held.has(role)
              const c = RESPONSIBILITY_COLORS[role]
              return (
                <button
                  key={role}
                  disabled={mut.isPending}
                  onClick={() => mut.mutate({ role, action: has ? 'revoke' : 'grant' })}
                  className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full transition-colors disabled:opacity-50"
                  style={{
                    background: has ? '#FEF2F2' : `${c}14`,
                    color: has ? '#dc2626' : c,
                    border: `1px solid ${has ? '#FECACA' : `${c}40`}`,
                  }}
                >
                  {has ? <Minus className="h-3 w-3" /> : <Plus className="h-3 w-3" />}
                  {has ? `Remove ${role}` : `Add ${role}`}
                </button>
              )
            })}
          </div>
        </div>
      )}
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Faculty lifecycle panel — H64.4
// ---------------------------------------------------------------------------

const FACULTY_STATUS_COLORS: Record<string, { bg: string; color: string; border: string }> = {
  ACTIVE:   { bg: 'rgba(34,197,94,0.12)',   color: '#16a34a', border: 'rgba(34,197,94,0.30)'   },
  INACTIVE: { bg: 'rgba(217,119,6,0.12)',   color: '#d97706', border: 'rgba(217,119,6,0.30)'   },
  ARCHIVED: { bg: 'rgba(100,116,139,0.12)', color: '#64748b', border: 'rgba(100,116,139,0.30)' },
}

function FacultyStatusBadge({ status }: { status: string }) {
  const c = FACULTY_STATUS_COLORS[status] ?? FACULTY_STATUS_COLORS.ACTIVE
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

function FacultyLifecyclePanel({ facultyId, canManage }: { facultyId: string; canManage: boolean }) {
  const qc = useQueryClient()
  const [selectedStatus, setSelectedStatus] = useState('')
  const [reason, setReason]                 = useState('')
  const [showHistory, setShowHistory]       = useState(false)

  const { data, isLoading } = useQuery<FacultyLifecycleStatusOut>({
    queryKey: ['sis-faculty-lifecycle', facultyId],
    queryFn:  () => sisApi.getFacultyLifecycle(facultyId),
    enabled:  canManage,
  })

  const transitionMut = useMutation({
    mutationFn: () => sisApi.transitionFacultyLifecycle(facultyId, selectedStatus, reason || undefined),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['sis-faculty-lifecycle', facultyId] })
      qc.invalidateQueries({ queryKey: ['sis-faculty-detail', facultyId] })
      qc.invalidateQueries({ queryKey: ['sis-faculty-directory'] })
      addToast(res.message, 'success')
      setSelectedStatus('')
      setReason('')
    },
    onError: (e) => addToast(getErrorMessage(e), 'error'),
  })

  if (!canManage) return null
  if (isLoading || !data) return (
    <div className="rounded-xl px-6 py-4 bg-white border border-gray-200 shadow-sm">
      <p className="text-sm text-gray-500">Loading lifecycle…</p>
    </div>
  )

  return (
    <div className="rounded-xl px-6 py-4 space-y-3 bg-white border border-gray-200 shadow-sm">

      <div className="flex items-center gap-2 pb-2 border-b border-gray-100">
        <Activity className="h-4 w-4 text-gray-400" />
        <h3 className="text-sm font-semibold text-gray-700">Lifecycle Status</h3>
      </div>

      <div className="flex items-center justify-between py-1">
        <span className="text-sm text-gray-500">Current status</span>
        <FacultyStatusBadge status={data.current_status} />
      </div>

      {data.allowed_next.length > 0 && (
        <div className="space-y-2 pt-1">
          <p className="text-xs text-gray-500">Change status (human ratification required):</p>
          <Select value={selectedStatus || undefined} onValueChange={setSelectedStatus}>
            <SelectTrigger className="w-full"><SelectValue placeholder="Select new status…" /></SelectTrigger>
            <SelectContent>
              {data.allowed_next.map(s => <SelectItem key={s} value={s}>{s}</SelectItem>)}
            </SelectContent>
          </Select>
          {selectedStatus && (
            <>
              <input
                type="text"
                placeholder="Reason (optional)"
                value={reason}
                onChange={e => setReason(e.target.value)}
                className="w-full px-3 py-2 text-sm rounded-lg bg-white border border-gray-300 text-gray-900 placeholder:text-gray-400 focus:outline-none focus:border-indigo-500"
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
        <p className="text-xs text-gray-500 py-1">This faculty member is archived. No further transitions available.</p>
      )}

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
                <div key={h.id} className="text-xs text-gray-500 flex items-start gap-2 py-1 border-b border-gray-100">
                  <span className="shrink-0 tabular-nums text-gray-400">{formatDt(h.changed_at)}</span>
                  <span>
                    {h.from_status
                      ? <><FacultyStatusBadge status={h.from_status} /> → <FacultyStatusBadge status={h.to_status} /></>
                      : <>Set to <FacultyStatusBadge status={h.to_status} /></>
                    }
                    {h.reason && <span className="ml-1 text-gray-500">— {h.reason}</span>}
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
// Edit form
// ---------------------------------------------------------------------------

function EditProfileForm({
  profile,
  onSave,
  onCancel,
}: {
  profile: FacultyDetailOut
  onSave: (body: FacultyProfileUpsert) => void
  onCancel: () => void
}) {
  const [form, setForm] = useState<FacultyProfileUpsert>({
    employee_id:           profile.employee_id ?? '',
    designation:           profile.designation ?? '',
    qualifications:        profile.qualifications ?? '',
    bio:                   profile.bio ?? '',
    office_location:       profile.office_location ?? '',
    phone:                 profile.phone ?? '',
    joining_date:          profile.joining_date ?? '',
    specialization:        profile.specialization ?? '',
    primary_department_id: profile.primary_department?.id ?? '',
  })

  const { data: departments } = useQuery({
    queryKey: ['acad-departments'],
    queryFn: () => academicsApi.listDepartments(),
  })

  function field(k: keyof FacultyProfileUpsert) {
    return {
      value: String(form[k] ?? ''),
      onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
        setForm(prev => ({ ...prev, [k]: e.target.value })),
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const body: FacultyProfileUpsert = { employee_id: form.employee_id }
    const optionals: (keyof FacultyProfileUpsert)[] = [
      'designation', 'qualifications', 'bio', 'office_location',
      'phone', 'joining_date', 'specialization', 'primary_department_id',
    ]
    for (const k of optionals) {
      const v = form[k]
      if (v) body[k] = v as any
    }
    onSave(body)
  }

  const inputCls = "w-full px-3 py-2 text-sm rounded-lg bg-white border border-gray-300 text-gray-900 placeholder:text-gray-400 focus:outline-none focus:border-indigo-500"

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label className="block text-xs text-gray-500 mb-1">Employee ID (legacy)</label>
          <input {...field('employee_id')} className={inputCls} placeholder="Optional" />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">Designation</label>
          <input {...field('designation')} className={inputCls} placeholder="Associate Professor" />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">Specialization</label>
          <input {...field('specialization')} className={inputCls} placeholder="Machine Learning" />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">Phone</label>
          <input {...field('phone')} className={inputCls} placeholder="+91 98765 43210" />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">Office Location</label>
          <input {...field('office_location')} className={inputCls} placeholder="Block A, Room 204" />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">Joining Date</label>
          <input type="date" {...field('joining_date')} className={inputCls} />
        </div>
        <div className="sm:col-span-2">
          <label className="block text-xs text-gray-500 mb-1">Primary Department</label>
          <Select
            value={String(form.primary_department_id ?? '') || 'NONE'}
            onValueChange={v => setForm(prev => ({ ...prev, primary_department_id: v === 'NONE' ? '' : v }))}
          >
            <SelectTrigger className="w-full"><SelectValue placeholder="None" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="NONE">None</SelectItem>
              {(departments ?? []).map(d => (
                <SelectItem key={d.id} value={d.id}>{d.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
      <div>
        <label className="block text-xs text-gray-500 mb-1">Qualifications</label>
        <textarea
          rows={2} {...field('qualifications')} className={inputCls}
          placeholder="Ph.D. Computer Science, IIT Bombay"
        />
      </div>
      <div>
        <label className="block text-xs text-gray-500 mb-1">Bio</label>
        <textarea rows={3} {...field('bio')} className={inputCls} placeholder="Short biography…" />
      </div>

      <div className="flex justify-end gap-2 pt-2">
        <Button type="button" variant="ghost" onClick={onCancel}>
          <X className="h-3.5 w-3.5 mr-1" /> Cancel
        </Button>
        <Button type="submit">
          <Save className="h-3.5 w-3.5 mr-1" /> Save profile
        </Button>
      </div>
    </form>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function FacultyProfilePage() {
  const { user_id } = useParams<{ user_id: string }>()
  const navigate    = useNavigate()
  const qc          = useQueryClient()
  const { user }    = useAuth()
  const canEdit     = user?.role === 'ADMIN' || user?.role === 'DEAN'
  const [editing, setEditing] = useState(false)

  const { data: profile, isLoading } = useQuery<FacultyDetailOut>({
    queryKey: ['sis-faculty-detail', user_id],
    queryFn:  () => sisApi.getFacultyDetail(user_id!),
    enabled:  !!user_id,
  })

  const saveMut = useMutation({
    mutationFn: (body: FacultyProfileUpsert) => sisApi.upsertFacultyProfile(user_id!, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sis-faculty-detail', user_id] })
      qc.invalidateQueries({ queryKey: ['sis-faculty-directory'] })
      addToast('Faculty profile saved.', 'success')
      setEditing(false)
    },
    onError: (e) => addToast(getErrorMessage(e), 'error'),
  })

  if (isLoading) return <PageLoading message="Loading faculty profile…" />
  if (!profile) return (
    <PageShell>
      <p className="text-center py-16 text-gray-500">Faculty member not found.</p>
    </PageShell>
  )

  const initials = profile.full_name.split(' ').map(p => p[0]).slice(0, 2).join('').toUpperCase()

  return (
    <PageShell width="sm">

      {/* Back */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => navigate(-1)}
          className="p-1.5 rounded-lg text-gray-400 hover:bg-gray-100 hover:text-gray-700 transition-colors"
        >
          <ArrowLeft className="h-5 w-5" />
        </button>
        <div className="flex-1 min-w-0">
          <h2 className="text-xl font-semibold text-gray-900 truncate">{profile.full_name}</h2>
          <p className="text-xs text-gray-500">{profile.email}</p>
        </div>
        {canEdit && !editing && (
          <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
            <Pencil className="h-3.5 w-3.5 mr-1" /> Edit
          </Button>
        )}
      </div>

      {/* Avatar strip */}
      <div className="rounded-xl p-5 flex items-center gap-4 bg-white border border-gray-200 shadow-sm">
        <div
          className="w-16 h-16 rounded-full flex items-center justify-center text-xl font-bold flex-shrink-0"
          style={{ background: 'rgba(16,185,129,0.12)', color: '#059669', border: '1px solid rgba(16,185,129,0.30)' }}
        >
          {initials}
        </div>
        <div>
          <p className="text-lg font-semibold text-gray-900">{profile.full_name}</p>
          {profile.designation && (
            <p className="text-sm text-gray-600">{profile.designation}</p>
          )}
          {profile.primary_department && (
            <p className="text-xs text-gray-500">{profile.primary_department.name}</p>
          )}
        </div>
        {profile.faculty_code && (
          <span
            className="ml-auto text-xs px-2 py-1 rounded font-mono"
            style={{ background: 'rgba(16,185,129,0.12)', color: '#059669', border: '1px solid rgba(16,185,129,0.25)' }}
          >
            {profile.faculty_code}
          </span>
        )}
      </div>

      {/* Edit form */}
      {editing && (
        <div className="rounded-xl px-6 py-5 bg-white border border-gray-200 shadow-sm">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">Edit faculty profile</h3>
          <EditProfileForm
            profile={profile}
            onSave={body => saveMut.mutate(body)}
            onCancel={() => setEditing(false)}
          />
        </div>
      )}

      {/* Faculty Identity */}
      <Card title="Faculty Identity" icon={BadgeCheck}>
        <InfoRow
          label="Faculty Code"
          value={profile.faculty_code
            ? <span className="font-mono">{profile.faculty_code}</span>
            : <span className="text-gray-400">Not assigned</span>}
        />
        <InfoRow
          label="Institution Email"
          value={profile.institution_email
            ? <span className="flex items-center gap-1 justify-end"><Mail className="h-3 w-3 text-gray-400" />{profile.institution_email}</span>
            : <span className="text-gray-400">Not assigned</span>}
        />
        <InfoRow
          label="Personal Login"
          value={<span className="flex items-center gap-1 justify-end"><KeyRound className="h-3 w-3 text-gray-400" />{profile.email}</span>}
        />
      </Card>

      {/* Responsibilities (display + management) */}
      {user_id && (
        <ResponsibilitiesCard
          facultyUserId={user_id}
          responsibilities={profile.responsibilities ?? []}
        />
      )}

      {/* Contact & Basics */}
      <Card title="Contact & Basics" icon={UserCheck}>
        <InfoRow label="Email"          value={profile.email} />
        {profile.phone    && <InfoRow label="Phone"     value={<span className="flex items-center gap-1 justify-end"><Phone className="h-3 w-3 text-gray-400" />{profile.phone}</span>} />}
        {profile.office_location && <InfoRow label="Office" value={<span className="flex items-center gap-1 justify-end"><MapPin className="h-3 w-3 text-gray-400" />{profile.office_location}</span>} />}
        {profile.joining_date && <InfoRow label="Joined" value={<span className="flex items-center gap-1 justify-end"><Calendar className="h-3 w-3 text-gray-400" />{profile.joining_date}</span>} />}
      </Card>

      {/* Academic */}
      <Card title="Academic Profile" icon={BookOpen}>
        {profile.qualifications && <InfoRow label="Qualifications" value={profile.qualifications} />}
        {profile.specialization  && <InfoRow label="Specialization"  value={profile.specialization} />}
        {profile.bio && (
          <div className="py-3">
            <p className="text-xs text-gray-500 mb-1">Bio</p>
            <p className="text-sm text-gray-700 leading-relaxed">{profile.bio}</p>
          </div>
        )}
        {!profile.qualifications && !profile.specialization && !profile.bio && (
          <p className="py-3 text-sm text-gray-500">No academic profile added yet.</p>
        )}
      </Card>

      {/* Department */}
      {profile.primary_department && (
        <Card title="Department" icon={Building2}>
          <InfoRow label="Name" value={profile.primary_department.name} />
          <InfoRow label="Code" value={profile.primary_department.code} />
        </Card>
      )}

      {/* Lifecycle panel — ADMIN / DEAN only */}
      {user_id && (
        <FacultyLifecyclePanel facultyId={user_id} canManage={canEdit} />
      )}

      {/* Teaching programs */}
      {(profile.teaching_programs?.length ?? 0) > 0 && (
        <Card title="Teaching Programs" icon={BookOpen}>
          <div className="space-y-1 pt-1">
            {profile.teaching_programs.map(p => (
              <div key={p.id} className="flex items-center justify-between py-2 border-b border-gray-100 last:border-0">
                <span className="text-sm text-gray-900">{p.name}</span>
                <span className="text-xs font-mono text-gray-500">{p.code}</span>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Governing programs (Dean only) */}
      {(profile.governing_programs?.length ?? 0) > 0 && (
        <Card title="Governing Programs" icon={ShieldCheck}>
          <div className="space-y-1 pt-1">
            {profile.governing_programs.map(p => (
              <div key={p.id} className="flex items-center justify-between py-2 border-b border-gray-100 last:border-0">
                <span className="text-sm text-gray-900">{p.name}</span>
                <span className="text-xs font-mono text-gray-500">{p.code}</span>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Course assignments */}
      <Card title="Active Course Assignments" icon={BookOpen}>
        {profile.active_assignments.length === 0 ? (
          <p className="py-3 text-sm text-gray-500">No active assignments.</p>
        ) : (
          <div className="space-y-2 pt-1">
            {profile.active_assignments.map((a, i) => (
              <div
                key={i}
                className="flex items-start justify-between gap-3 py-2 border-b border-gray-100 last:border-0"
              >
                <div>
                  <p className="text-sm text-gray-900">{a.course.name}</p>
                  <p className="text-xs text-gray-500 font-mono">{a.course.code} · {a.semester_label}</p>
                </div>
                <RoleChip role={a.role} />
              </div>
            ))}
          </div>
        )}
      </Card>

    </PageShell>
  )
}
