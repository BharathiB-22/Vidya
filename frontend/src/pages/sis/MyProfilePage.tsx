/**
 * H51 — Self-Service Profile Page (/sis/me/profile)
 *
 * STUDENT: reads/edits contact + emergency contact fields.
 * FACULTY: reads/edits contact + bio + specialization fields.
 *
 * Admin-assigned fields (USN, employee ID, designation, program, etc.)
 * are displayed read-only and cannot be changed here.
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  UserCircle2, Phone, MapPin, BookOpen, Pencil, Save, X, Shield,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { PageLoading } from '@/components/shared/PageLoading'
import { addToast } from '@/hooks/useToast'
import { getErrorMessage } from '@/lib/api'
import { useAuth } from '@/lib/auth'
import { sisApi } from '@/lib/api/sis'
import type {
  StudentDetailOut, FacultyDetailOut,
  StudentSelfServiceUpdate, FacultySelfServiceUpdate,
} from '@/lib/api/sis'

// ---------------------------------------------------------------------------
// Shared display helpers
// ---------------------------------------------------------------------------

// Responsibility-chip colors (GUIDE / EVALUATOR / BOARD / DEAN)
const MY_RESP_COLORS: Record<string, string> = {
  GUIDE: '#818cf8', EVALUATOR: '#34d399', BOARD: '#fbbf24', DEAN: '#f472b6',
}

function InfoRow({ label, value, mono = false }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div
      className="flex items-start justify-between py-3 gap-4"
      style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}
    >
      <span className="text-sm text-slate-500 flex-shrink-0">{label}</span>
      <span className={`text-sm text-slate-200 font-medium text-right ${mono ? 'font-mono' : ''}`}>
        {value || <span className="text-slate-600">—</span>}
      </span>
    </div>
  )
}

function Card({ title, icon: Icon, locked = false, children }: {
  title: string; icon: typeof UserCircle2; locked?: boolean; children: React.ReactNode
}) {
  return (
    <div
      className="rounded-xl px-6 py-4 space-y-1"
      style={{ background: 'rgba(12,22,41,0.85)', border: '1px solid rgba(255,255,255,0.08)' }}
    >
      <div className="flex items-center gap-2 pb-2" style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
        <Icon className="h-4 w-4 text-slate-500" />
        <h3 className="text-sm font-semibold text-slate-400">{title}</h3>
        {locked && (
          <span className="ml-auto flex items-center gap-1 text-xs text-slate-600">
            <Shield className="h-3 w-3" /> Admin-managed
          </span>
        )}
      </div>
      {children}
    </div>
  )
}

const inputCls = "w-full px-3 py-2 text-sm rounded-lg bg-white/5 border border-white/10 text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
const labelCls = "block text-xs text-slate-500 mb-1"

// ---------------------------------------------------------------------------
// Student self-service view
// ---------------------------------------------------------------------------

function StudentProfileView({ profile }: { profile: StudentDetailOut }) {
  const qc = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState<StudentSelfServiceUpdate>({
    phone:                   profile.phone ?? '',
    address_line1:           profile.address_line1 ?? '',
    address_city:            profile.address_city ?? '',
    address_state:           profile.address_state ?? '',
    emergency_contact_name:  profile.emergency_contact_name ?? '',
    emergency_contact_phone: profile.emergency_contact_phone ?? '',
  })

  const saveMut = useMutation({
    mutationFn: () => {
      const body: StudentSelfServiceUpdate = {}
      if (form.phone)                   body.phone = form.phone
      if (form.address_line1)           body.address_line1 = form.address_line1
      if (form.address_city)            body.address_city = form.address_city
      if (form.address_state)           body.address_state = form.address_state
      if (form.emergency_contact_name)  body.emergency_contact_name = form.emergency_contact_name
      if (form.emergency_contact_phone) body.emergency_contact_phone = form.emergency_contact_phone
      return sisApi.updateMyStudentProfile(body)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['my-student-profile'] })
      addToast('Profile updated.', 'success')
      setEditing(false)
    },
    onError: (e) => addToast(getErrorMessage(e), 'error'),
  })

  function field(k: keyof StudentSelfServiceUpdate) {
    return {
      value: String(form[k] ?? ''),
      onChange: (e: React.ChangeEvent<HTMLInputElement>) =>
        setForm(prev => ({ ...prev, [k]: e.target.value })),
    }
  }

  const initials = profile.full_name.split(' ').map(p => p[0]).slice(0, 2).join('').toUpperCase()

  return (
    <>
      {/* Avatar strip */}
      <div
        className="rounded-xl p-5 flex items-center gap-4"
        style={{ background: 'rgba(12,22,41,0.85)', border: '1px solid rgba(255,255,255,0.08)' }}
      >
        <div
          className="w-16 h-16 rounded-full flex items-center justify-center text-xl font-bold flex-shrink-0"
          style={{ background: 'rgba(99,102,241,0.15)', color: '#a5b4fc', border: '1px solid rgba(99,102,241,0.3)' }}
        >
          {initials}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-lg font-semibold text-slate-100">{profile.full_name}</p>
          <p className="text-sm text-slate-400">{profile.email}</p>
          {profile.program && (
            <p className="text-xs text-slate-500 mt-0.5">
              {profile.program.name} · {profile.program.degree_type}
            </p>
          )}
        </div>
        {!editing && (
          <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
            <Pencil className="h-3.5 w-3.5 mr-1" /> Edit
          </Button>
        )}
      </div>

      {/* Admin-managed identity — read-only */}
      <Card title="Academic Identity" icon={UserCircle2} locked>
        <InfoRow label="Email"      value={profile.email} />
        <InfoRow label="Identifier" value={profile.identifier} />
        {profile.usn && <InfoRow label="USN" value={profile.usn} mono />}
        {profile.admission_year && <InfoRow label="Admission year" value={String(profile.admission_year)} />}
        {profile.program && <InfoRow label="Program" value={`${profile.program.name} (${profile.program.code})`} />}
        {profile.department && <InfoRow label="Department" value={profile.department.name} />}
        {profile.batch && <InfoRow label="Batch" value={`${profile.batch.name} (${profile.batch.start_year}–${profile.batch.end_year})`} />}
        {profile.current_section && <InfoRow label="Section" value={`Section ${profile.current_section.name}`} />}
      </Card>

      {/* Editable contact details */}
      {editing ? (
        <div
          className="rounded-xl px-6 py-5"
          style={{ background: 'rgba(12,22,41,0.85)', border: '1px solid rgba(255,255,255,0.08)' }}
        >
          <div className="flex items-center gap-2 pb-3 mb-3" style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
            <Phone className="h-4 w-4 text-slate-500" />
            <h3 className="text-sm font-semibold text-slate-400">Edit contact details</h3>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className={labelCls}>Phone</label>
              <input {...field('phone')} className={inputCls} placeholder="+91 98765 43210" />
            </div>
            <div>
              <label className={labelCls}>Address line</label>
              <input {...field('address_line1')} className={inputCls} placeholder="Flat 4B, XYZ Apartments" />
            </div>
            <div>
              <label className={labelCls}>City</label>
              <input {...field('address_city')} className={inputCls} placeholder="Bengaluru" />
            </div>
            <div>
              <label className={labelCls}>State</label>
              <input {...field('address_state')} className={inputCls} placeholder="Karnataka" />
            </div>
            <div>
              <label className={labelCls}>Emergency contact name</label>
              <input {...field('emergency_contact_name')} className={inputCls} placeholder="Parent / Guardian name" />
            </div>
            <div>
              <label className={labelCls}>Emergency contact phone</label>
              <input {...field('emergency_contact_phone')} className={inputCls} placeholder="+91 98765 43210" />
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-4">
            <Button type="button" variant="ghost" onClick={() => setEditing(false)}>
              <X className="h-3.5 w-3.5 mr-1" /> Cancel
            </Button>
            <Button onClick={() => saveMut.mutate()} disabled={saveMut.isPending}>
              <Save className="h-3.5 w-3.5 mr-1" />
              {saveMut.isPending ? 'Saving…' : 'Save'}
            </Button>
          </div>
        </div>
      ) : (
        <Card title="Contact Details" icon={Phone}>
          <InfoRow label="Phone"              value={profile.phone} />
          <InfoRow label="Address"            value={profile.address_line1} />
          <InfoRow label="City"               value={profile.address_city} />
          <InfoRow label="State"              value={profile.address_state} />
          <InfoRow label="Emergency contact"  value={profile.emergency_contact_name} />
          <InfoRow label="Emergency phone"    value={profile.emergency_contact_phone} />
          {!profile.phone && !profile.address_line1 && (
            <p className="py-2 text-xs text-slate-500">No contact details added yet. Click Edit to add yours.</p>
          )}
        </Card>
      )}
    </>
  )
}

// ---------------------------------------------------------------------------
// Faculty self-service view
// ---------------------------------------------------------------------------

function FacultyProfileView({ profile }: { profile: FacultyDetailOut }) {
  const qc = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState<FacultySelfServiceUpdate>({
    phone:           profile.phone ?? '',
    office_location: profile.office_location ?? '',
    bio:             profile.bio ?? '',
    specialization:  profile.specialization ?? '',
  })

  const saveMut = useMutation({
    mutationFn: () => {
      const body: FacultySelfServiceUpdate = {}
      if (form.phone)           body.phone = form.phone
      if (form.office_location) body.office_location = form.office_location
      if (form.bio)             body.bio = form.bio
      if (form.specialization)  body.specialization = form.specialization
      return sisApi.updateMyFacultyProfile(body)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['my-faculty-profile'] })
      addToast('Profile updated.', 'success')
      setEditing(false)
    },
    onError: (e) => addToast(getErrorMessage(e), 'error'),
  })

  function field(k: keyof FacultySelfServiceUpdate) {
    return {
      value: String(form[k] ?? ''),
      onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
        setForm(prev => ({ ...prev, [k]: e.target.value })),
    }
  }

  const initials = profile.full_name.split(' ').map(p => p[0]).slice(0, 2).join('').toUpperCase()

  return (
    <>
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
        <div className="flex-1 min-w-0">
          <p className="text-lg font-semibold text-slate-100">{profile.full_name}</p>
          <p className="text-sm text-slate-400">{profile.email}</p>
          {profile.designation && <p className="text-xs text-slate-500 mt-0.5">{profile.designation}</p>}
          {profile.primary_department && <p className="text-xs text-slate-600">{profile.primary_department.name}</p>}
        </div>
        {!editing && (
          <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
            <Pencil className="h-3.5 w-3.5 mr-1" /> Edit
          </Button>
        )}
      </div>

      {/* Admin-managed identity — read-only */}
      <Card title="Academic Identity" icon={UserCircle2} locked>
        <InfoRow label="Email"         value={profile.email} />
        {profile.faculty_code && <InfoRow label="Faculty code" value={profile.faculty_code} mono />}
        {profile.institution_email && <InfoRow label="Institution email" value={profile.institution_email} />}
        {profile.designation  && <InfoRow label="Designation"  value={profile.designation} />}
        {profile.qualifications && <InfoRow label="Qualifications" value={profile.qualifications} />}
        {profile.joining_date && <InfoRow label="Joining date" value={profile.joining_date} />}
        {profile.primary_department && <InfoRow label="Department" value={profile.primary_department.name} />}
      </Card>

      {/* My Responsibilities — explains why certain dashboards are visible */}
      <Card title="My Responsibilities" icon={Shield} locked>
        {(profile.responsibilities ?? []).length === 0 ? (
          <p className="py-2 text-xs text-slate-500">
            No additional responsibilities. You have the base Faculty role.
          </p>
        ) : (
          <div className="py-2 flex flex-wrap gap-2">
            {profile.responsibilities.map(r => {
              const c = MY_RESP_COLORS[r] ?? '#94a3b8'
              return (
                <span key={r}
                  className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full"
                  style={{ background: `${c}1F`, color: c, border: `1px solid ${c}40` }}>
                  <Shield className="h-3 w-3" />{r}
                </span>
              )
            })}
          </div>
        )}
        <p className="pt-1 pb-1 text-[11px] text-slate-600">
          Responsibilities are granted by your Dean or Admin and control which dashboards you can access.
        </p>
      </Card>

      {/* Editable contact + bio */}
      {editing ? (
        <div
          className="rounded-xl px-6 py-5"
          style={{ background: 'rgba(12,22,41,0.85)', border: '1px solid rgba(255,255,255,0.08)' }}
        >
          <div className="flex items-center gap-2 pb-3 mb-3" style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
            <BookOpen className="h-4 w-4 text-slate-500" />
            <h3 className="text-sm font-semibold text-slate-400">Edit contact & bio</h3>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className={labelCls}>Phone</label>
              <input {...field('phone')} className={inputCls} placeholder="+91 98765 43210" />
            </div>
            <div>
              <label className={labelCls}>Office location</label>
              <input {...field('office_location')} className={inputCls} placeholder="Block A, Room 204" />
            </div>
            <div>
              <label className={labelCls}>Specialization</label>
              <input {...field('specialization')} className={inputCls} placeholder="Machine Learning" />
            </div>
          </div>
          <div className="mt-4">
            <label className={labelCls}>Bio</label>
            <textarea rows={4} {...field('bio')} className={inputCls} placeholder="Short biography visible to students…" />
          </div>
          <div className="flex justify-end gap-2 pt-4">
            <Button type="button" variant="ghost" onClick={() => setEditing(false)}>
              <X className="h-3.5 w-3.5 mr-1" /> Cancel
            </Button>
            <Button onClick={() => saveMut.mutate()} disabled={saveMut.isPending}>
              <Save className="h-3.5 w-3.5 mr-1" />
              {saveMut.isPending ? 'Saving…' : 'Save'}
            </Button>
          </div>
        </div>
      ) : (
        <Card title="Contact & Bio" icon={Phone}>
          <InfoRow label="Phone"          value={profile.phone} />
          <InfoRow label="Office"         value={<span className="flex items-center gap-1"><MapPin className="h-3 w-3 text-slate-500" />{profile.office_location}</span>} />
          <InfoRow label="Specialization" value={profile.specialization} />
          {profile.bio && (
            <div className="py-3">
              <p className="text-xs text-slate-500 mb-1">Bio</p>
              <p className="text-sm text-slate-300 leading-relaxed">{profile.bio}</p>
            </div>
          )}
          {!profile.phone && !profile.office_location && !profile.bio && (
            <p className="py-2 text-xs text-slate-500">No contact details added yet. Click Edit to add yours.</p>
          )}
        </Card>
      )}

      {/* Active assignments — read-only */}
      {profile.active_assignments.length > 0 && (
        <Card title="My Active Assignments" icon={BookOpen}>
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
                <span
                  className="text-xs px-2 py-0.5 rounded flex-shrink-0"
                  style={{ background: 'rgba(99,102,241,0.15)', color: '#a5b4fc', border: '1px solid rgba(99,102,241,0.25)' }}
                >
                  {a.role.replace('_', ' ')}
                </span>
              </div>
            ))}
          </div>
        </Card>
      )}
    </>
  )
}

// ---------------------------------------------------------------------------
// Root page — dispatches to student or faculty view based on role
// ---------------------------------------------------------------------------

export default function MyProfilePage() {
  const { user } = useAuth()
  const isStudent = user?.role === 'STUDENT'
  const isFaculty = user?.role === 'FACULTY'

  const studentQ = useQuery<StudentDetailOut>({
    queryKey: ['my-student-profile'],
    queryFn:  sisApi.getMyStudentProfile,
    enabled:  isStudent,
  })

  const facultyQ = useQuery<FacultyDetailOut>({
    queryKey: ['my-faculty-profile'],
    queryFn:  sisApi.getMyFacultyProfile,
    enabled:  isFaculty,
  })

  const isLoading = (isStudent && studentQ.isLoading) || (isFaculty && facultyQ.isLoading)

  if (isLoading) return <PageLoading message="Loading your profile…" />

  return (
    <PageShell width="sm">
      <PageHeader
        icon={UserCircle2}
        title="My Profile"
        subtitle="View your academic identity and update your contact details"
      />

      {isStudent && studentQ.data && (
        <StudentProfileView profile={studentQ.data} />
      )}

      {isFaculty && facultyQ.data && (
        <FacultyProfileView profile={facultyQ.data} />
      )}

      {!isStudent && !isFaculty && (
        <div className="py-16 text-center">
          <p className="text-slate-500 text-sm">Profile self-service is available for Students and Faculty only.</p>
        </div>
      )}
    </PageShell>
  )
}
