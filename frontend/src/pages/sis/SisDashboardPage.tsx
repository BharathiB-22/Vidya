import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  School2, Building2, GraduationCap, CalendarRange, LayoutList, Calendar, Users,
} from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { PageLoading } from '@/components/shared/PageLoading'
import { sisApi } from '@/lib/api/sis'
import type { DashboardCounts } from '@/lib/api/sis'
import type { LucideIcon } from 'lucide-react'

interface KpiCardProps {
  label: string
  value: number | string
  icon: LucideIcon
  to?: string
  accentColor: string
}

function KpiCard({ label, value, icon: Icon, to, accentColor }: KpiCardProps) {
  const navigate = useNavigate()
  return (
    <button
      onClick={() => to && navigate(to)}
      className="w-full text-left rounded-xl p-5 flex items-center gap-4 transition-all hover:scale-[1.01]"
      style={{
        background: 'rgba(255,255,255,0.03)',
        border: '1px solid rgba(255,255,255,0.08)',
        cursor: to ? 'pointer' : 'default',
      }}
    >
      <div
        className="w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0"
        style={{ background: `${accentColor}18`, border: `1px solid ${accentColor}30` }}
      >
        <Icon className="h-5 w-5" style={{ color: accentColor }} />
      </div>
      <div>
        <p className="text-3xl font-bold text-slate-100 leading-tight">{value}</p>
        <p className="text-sm font-medium text-slate-500 mt-0.5">{label}</p>
      </div>
    </button>
  )
}

export default function SisDashboardPage() {
  const { data: counts, isLoading } = useQuery<DashboardCounts>({
    queryKey: ['sis-dashboard-counts'],
    queryFn: sisApi.getDashboardCounts,
  })

  const kpis: (KpiCardProps & { key: string })[] = [
    {
      key: 'schools', label: 'Schools', icon: School2, to: '/sis/schools',
      value: counts?.schools ?? '–', accentColor: '#6366f1',
    },
    {
      key: 'depts', label: 'Departments', icon: Building2, to: '/sis/departments',
      value: counts?.departments ?? '–', accentColor: '#8b5cf6',
    },
    {
      key: 'programs', label: 'Programs', icon: GraduationCap,
      value: counts?.programs ?? '–', accentColor: '#3b82f6',
    },
    {
      key: 'batches', label: 'Active Batches', icon: CalendarRange,
      value: counts?.active_batches ?? '–', accentColor: '#10b981',
    },
    {
      key: 'semesters', label: 'Semesters', icon: Calendar,
      value: counts?.semesters ?? '–', accentColor: '#f59e0b',
    },
    {
      key: 'sections', label: 'Sections', icon: LayoutList,
      value: counts?.sections ?? '–', accentColor: '#ec4899',
    },
    {
      key: 'enrolled', label: 'Enrolled Students', icon: Users, to: '/sis/roster',
      value: counts?.enrolled_students ?? '–', accentColor: '#34d399',
    },
  ]

  return (
    <PageShell>
      <PageHeader
        icon={School2}
        title="Enrollment Overview"
        subtitle="Your institution's academic structure and student enrollment at a glance"
      />

      {isLoading ? (
        <PageLoading message="Loading SIS data…" />
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {kpis.map(({ key, ...props }) => (
            <KpiCard key={key} {...props} />
          ))}
        </div>
      )}

      <div className="mt-4 rounded-xl p-4 text-sm text-slate-500"
        style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)' }}>
        <p className="font-medium text-slate-400 mb-2">Quick actions</p>
        <ul className="space-y-1 text-xs">
          <li>→ <span className="text-slate-300 cursor-pointer hover:underline"
            onClick={() => {}}>Enrollment Roster</span> — view or modify which students are in each section</li>
          <li>→ <span className="text-slate-300">Academic Structure</span> — manage departments, programs, batches, semesters and sections under <em>Academic Structure</em> in the sidebar</li>
          <li>→ <span className="text-slate-300">Bulk Onboarding</span> — import students and auto-assign them to sections via CSV</li>
        </ul>
      </div>
    </PageShell>
  )
}
