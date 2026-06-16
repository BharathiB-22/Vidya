import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft, UserCheck, BookOpen, Building2, Phone, MapPin, Calendar, Pencil, X, Save,
  Activity, ChevronDown,
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
import { academicsApi } from '@/lib/api/academics'
import { useAuth } from '@/lib/auth'

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div
      className="flex items-start justify-between py-3 gap-4"
      style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}
    >
      <span className="text-sm text-slate-500 flex-shrink-0">{label}</span>
      <span className="text-sm text-slate-200 font-medium text-right">{value || '—'}</span>
    </div>
  )
}

function Card({ title, icon: Icon, children }: { title: string; icon: typeof UserCheck; children: React.ReactNode }) {
  return (
    <div
      className="rounded-xl px-6 py-4 space-y-1"
      style={{ background: 'rgba(12,22,41,0.85)', border: '1px solid rgba(255,255,255,0.08)' }}
    >
      <div className="flex items-center gap-2 pb-2" style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
        <Icon className="h-4 w-4 text-slate-500" />
        <h3 className="text-sm font-semibold text-slate-400">{title}</h3>
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
// Faculty lifecycle panel — H64.4
// ---------------------------------------------------------------------------

const FACULTY_STATUS_COLORS: Record<string, { bg: string; color: string; border: string }> = {
  ACTIVE:   { bg: 'rgba(34,197,94,0.12)',   color: '#4ade80', border: 'rgba(34,197,94,0.25)'   },
  INACTIVE: { bg: 'rgba(251,191,36,0.12)',  color: '#fbbf24', border: 'rgba(251,191,36,0.25)'  },
  ARCHIVED: { bg: 'rgba(100,116,139,0.12)', color: '#94a3b8', border: 'rgba(100,116,139,0.25)' },
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
    <div className="rounded-xl px-6 py-4" style={{ background: 'rgba(12,22,41,0.85)', border: '1px solid rgba(255,255,255,0.08)' }}>
      <p className="text-sm text-slate-500">Loading lifecycle…</p>
    </div>
  )

  return (
    <div className="rounded-xl px-6 py-4 space-y-3"
      style={{ background: 'rgba(12,22,41,0.85)', border: '1px solid rgba(255,255,255,0.08)' }}>

      <div className="flex items-center gap-2 pb-2" style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
        <Activity className="h-4 w-4 text-slate-500" />
        <h3 className="text-sm font-semibold text-slate-400">Lifecycle Status</h3>
      </div>

      <div className="flex items-center justify-between py-1">
        <span className="text-sm text-slate-500">Current status</span>
        <FacultyStatusBadge status={data.current_status} />
      </div>

      {data.allowed_next.length > 0 && (
        <div className="space-y-2 pt-1">
          <p className="text-xs text-slate-500">Change status (human ratification required):</p>
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
                className="w-full px-3 py-2 text-sm rounded-lg bg-white/5 border border-white/10 text-slate-200 placeholder:text-slate-600"
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
        <p className="text-xs text-slate-500 py-1">This faculty member is archived. No further transitions available.</p>
      )}

      {data.history.length > 0 && (
        <div className="pt-2">
          <button
            onClick={() => setShowHistory(v => !v)}
            className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-300 transition-colors"
          >
            <ChevronDown size={12} className={showHistory ? 'rotate-180 transition-transform' : 'transition-transform'} />
            {showHistory ? 'Hide' : 'Show'} history ({data.history.length})
          </button>
          {showHistory && (
            <div className="mt-2 space-y-1">
              {data.history.map(h => (
                <div key={h.id} className="text-xs text-slate-400 flex items-start gap-2 py-1"
                  style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                  <span className="shrink-0 tabular-nums text-slate-600">{formatDt(h.changed_at)}</span>
                  <span>
                    {h.from_status
                      ? <><FacultyStatusBadge status={h.from_status} /> → <FacultyStatusBadge status={h.to_status} /></>
                      : <>Set to <FacultyStatusBadge status={h.to_status} /></>
                    }
                    {h.reason && <span className="ml-1 text-slate-500">— {h.reason}</span>}
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

  const inputCls = "w-full px-3 py-2 text-sm rounded-lg bg-white/5 border border-white/10 text-slate-200 focus:outline-none focus:border-indigo-500"

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label className="block text-xs text-slate-500 mb-1">Employee ID *</label>
          <input required {...field('employee_id')} className={inputCls} placeholder="EMP-001" />
        </div>
        <div>
          <label className="block text-xs text-slate-500 mb-1">Designation</label>
          <input {...field('designation')} className={inputCls} placeholder="Associate Professor" />
        </div>
        <div>
          <label className="block text-xs text-slate-500 mb-1">Specialization</label>
          <input {...field('specialization')} className={inputCls} placeholder="Machine Learning" />
        </div>
        <div>
          <label className="block text-xs text-slate-500 mb-1">Phone</label>
          <input {...field('phone')} className={inputCls} placeholder="+91 98765 43210" />
        </div>
        <div>
          <label className="block text-xs text-slate-500 mb-1">Office Location</label>
          <input {...field('office_location')} className={inputCls} placeholder="Block A, Room 204" />
        </div>
        <div>
          <label className="block text-xs text-slate-500 mb-1">Joining Date</label>
          <input type="date" {...field('joining_date')} className={inputCls} />
        </div>
        <div className="sm:col-span-2">
          <label className="block text-xs text-slate-500 mb-1">Primary Department</label>
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
        <label className="block text-xs text-slate-500 mb-1">Qualifications</label>
        <textarea
          rows={2} {...field('qualifications')} className={inputCls}
          placeholder="Ph.D. Computer Science, IIT Bombay"
        />
      </div>
      <div>
        <label className="block text-xs text-slate-500 mb-1">Bio</label>
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
      <p className="text-center py-16 text-slate-500">Faculty member not found.</p>
    </PageShell>
  )

  const initials = profile.full_name.split(' ').map(p => p[0]).slice(0, 2).join('').toUpperCase()

  return (
    <PageShell width="sm">

      {/* Back */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => navigate(-1)}
          className="p-1.5 rounded-lg text-slate-600 hover:bg-white/6 hover:text-slate-300 transition-colors"
        >
          <ArrowLeft className="h-5 w-5" />
        </button>
        <div className="flex-1 min-w-0">
          <h2 className="text-xl font-semibold text-slate-100 truncate">{profile.full_name}</h2>
          <p className="text-xs text-slate-500">{profile.email}</p>
        </div>
        {canEdit && !editing && (
          <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
            <Pencil className="h-3.5 w-3.5 mr-1" /> Edit
          </Button>
        )}
      </div>

      {/* Avatar strip */}
      <div
        className="rounded-xl p-5 flex items-center gap-4"
        style={{ background: 'rgba(12,22,41,0.85)', border: '1px solid rgba(255,255,255,0.08)' }}
      >
        <div
          className="w-16 h-16 rounded-full flex items-center justify-center text-xl font-bold flex-shrink-0"
          style={{ background: 'rgba(16,185,129,0.15)', color: '#34d399', border: '1px solid rgba(16,185,129,0.3)' }}
        >
          {initials}
        </div>
        <div>
          <p className="text-lg font-semibold text-slate-100">{profile.full_name}</p>
          {profile.designation && (
            <p className="text-sm text-slate-400">{profile.designation}</p>
          )}
          {profile.primary_department && (
            <p className="text-xs text-slate-500">{profile.primary_department.name}</p>
          )}
        </div>
        {profile.employee_id && (
          <span
            className="ml-auto text-xs px-2 py-1 rounded font-mono"
            style={{ background: 'rgba(16,185,129,0.12)', color: '#34d399', border: '1px solid rgba(16,185,129,0.25)' }}
          >
            {profile.employee_id}
          </span>
        )}
      </div>

      {/* Edit form */}
      {editing && (
        <div
          className="rounded-xl px-6 py-5"
          style={{ background: 'rgba(12,22,41,0.85)', border: '1px solid rgba(255,255,255,0.08)' }}
        >
          <h3 className="text-sm font-semibold text-slate-400 mb-4">Edit faculty profile</h3>
          <EditProfileForm
            profile={profile}
            onSave={body => saveMut.mutate(body)}
            onCancel={() => setEditing(false)}
          />
        </div>
      )}

      {/* Contact & Basics */}
      <Card title="Contact & Basics" icon={UserCheck}>
        <InfoRow label="Email"          value={profile.email} />
        <InfoRow label="Institution email" value={
          profile.institution_email
            ? <span className="font-mono" style={{ color: '#374151' }}>{profile.institution_email}</span>
            : <span style={{ color: '#9CA3AF' }}>Not generated</span>
        } />
        {profile.phone    && <InfoRow label="Phone"     value={<span className="flex items-center gap-1"><Phone className="h-3 w-3 text-slate-500" />{profile.phone}</span>} />}
        {profile.office_location && <InfoRow label="Office" value={<span className="flex items-center gap-1"><MapPin className="h-3 w-3 text-slate-500" />{profile.office_location}</span>} />}
        {profile.joining_date && <InfoRow label="Joined" value={<span className="flex items-center gap-1"><Calendar className="h-3 w-3 text-slate-500" />{profile.joining_date}</span>} />}
      </Card>

      {/* Academic */}
      <Card title="Academic Profile" icon={BookOpen}>
        {profile.qualifications && <InfoRow label="Qualifications" value={profile.qualifications} />}
        {profile.specialization  && <InfoRow label="Specialization"  value={profile.specialization} />}
        {profile.bio && (
          <div className="py-3">
            <p className="text-xs text-slate-500 mb-1">Bio</p>
            <p className="text-sm text-slate-300 leading-relaxed">{profile.bio}</p>
          </div>
        )}
        {!profile.qualifications && !profile.specialization && !profile.bio && (
          <p className="py-3 text-sm text-slate-500">No academic profile added yet.</p>
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

      {/* Course assignments */}
      <Card title="Active Course Assignments" icon={BookOpen}>
        {profile.active_assignments.length === 0 ? (
          <p className="py-3 text-sm text-slate-500">No active assignments.</p>
        ) : (
          <div className="space-y-2 pt-1">
            {profile.active_assignments.map((a, i) => (
              <div
                key={i}
                className="flex items-start justify-between gap-3 py-2"
                style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}
              >
                <div>
                  <p className="text-sm text-slate-200">{a.course.name}</p>
                  <p className="text-xs text-slate-500 font-mono">{a.course.code} · {a.semester_label}</p>
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
