import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { BookOpen } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { PageLoading } from '@/components/shared/PageLoading'
import { PageEmpty } from '@/components/shared/PageEmpty'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { SyllabusStatusBadge } from '@/components/syllabus/SyllabusStatusBadge'
import { assignmentsApi } from '@/lib/api/assignments'
import { listSyllabuses } from '@/lib/api/syllabuses'
import { sisApi } from '@/lib/api/sis'
import { ownershipApi } from '@/lib/api/ownership'
import type { Syllabus } from '@/types/syllabus'
import { FACULTY_SUBJECT_TABS } from '@/components/faculty/subjects/tabRegistry'
import type { FacultySubjectContext } from '@/components/faculty/subjects/tabs/types'

// A course typically carries one live syllabus, but versions/forks can leave
// several records — prefer the most authoritative status, then latest version.
const STATUS_RANK: Record<string, number> = {
  DEAN_LOCKED: 0,
  DEAN_APPROVED: 1,
  PENDING_REVIEW: 2,
  DRAFT: 3,
  REJECTED: 4,
  AI_GENERATING: 5,
}

function pickSyllabus(items: Syllabus[] | undefined): Syllabus | null {
  if (!items || items.length === 0) return null
  const sorted = [...items].sort((a, b) => {
    const rankDiff = (STATUS_RANK[a.status] ?? 9) - (STATUS_RANK[b.status] ?? 9)
    return rankDiff !== 0 ? rankDiff : b.version - a.version
  })
  return sorted[0]
}

export default function FacultySubjectWorkspacePage() {
  const { assignmentId } = useParams<{ assignmentId: string }>()
  const [activeTab, setActiveTab] = useState('overview')

  const { data: mine, isLoading: mineLoading, isError: mineError } = useQuery({
    queryKey: ['my-assignments'],
    queryFn: () => assignmentsApi.listMine(),
  })
  const assignment = mine?.items.find((a) => a.id === assignmentId)

  const { data: syllabuses, isLoading: syllabusLoading } = useQuery({
    queryKey: ['syllabuses', 'for-workspace', assignment?.course_id],
    queryFn: () => listSyllabuses({ course_id: assignment!.course_id }),
    enabled: !!assignment?.course_id,
  })

  const { data: facultyProfile } = useQuery({
    queryKey: ['my-faculty-profile'],
    queryFn: sisApi.getMyFacultyProfile,
  })

  const { data: responsibilities } = useQuery({
    queryKey: ['faculty-responsibilities'],
    queryFn: ownershipApi.getFacultyResponsibilities,
  })

  if (mineLoading || (assignment && syllabusLoading)) {
    return (
      <PageShell>
        <PageLoading message="Loading subject…" />
      </PageShell>
    )
  }

  if (mineError || !assignment) {
    return (
      <PageShell>
        <PageEmpty
          icon={BookOpen}
          title="Subject not found"
          message="This course is not assigned to you, or the assignment no longer exists."
        />
      </PageShell>
    )
  }

  const syllabus = pickSyllabus(syllabuses?.items)
  const courseEntry = responsibilities?.course_assignments.find((c) => c.assignment_id === assignmentId)
  const sectionsHandled = [
    ...new Set(
      (mine?.items ?? [])
        .filter((a) => a.course_id === assignment.course_id && a.section?.name)
        .map((a) => a.section!.name)
    ),
  ]

  const ctx: FacultySubjectContext = {
    assignment,
    syllabusId: syllabus?.id ?? null,
    syllabusStatus: syllabus?.status ?? null,
    departmentName: courseEntry?.department_name ?? null,
    facultyName: facultyProfile?.full_name ?? null,
    sectionsHandled,
  }

  return (
    <PageShell>
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        {/* Sticky header + tab bar — stays in view while a tab's content scrolls */}
        <div className="sticky top-0 z-10 -mx-6 px-6 pt-6 pb-3 bg-gray-50 border-b border-gray-200 space-y-4">
          <PageHeader
            icon={BookOpen}
            title={`${assignment.course?.code ?? ''} — ${assignment.course?.title ?? 'Subject'}`}
            subtitle={[
              'Credits: Not configured',
              assignment.semester
                ? `Semester ${assignment.semester.number}${assignment.semester.label ? ` — ${assignment.semester.label}` : ''}`
                : null,
              `Section${sectionsHandled.length > 1 ? 's' : ''} ${sectionsHandled.join(', ') || (assignment.section?.name ?? '—')}`,
              ctx.departmentName ?? 'Department not on record',
            ].filter(Boolean).join(' · ')}
            action={
              <div className="flex flex-col items-end gap-1.5">
                {ctx.facultyName && <span className="text-sm font-medium text-gray-700">{ctx.facultyName}</span>}
                {ctx.syllabusStatus && <SyllabusStatusBadge status={ctx.syllabusStatus} viewerRole="FACULTY" />}
              </div>
            }
          />

          <div className="overflow-x-auto pb-1">
            <TabsList className="w-max">
              {FACULTY_SUBJECT_TABS.map((tab) => (
                <TabsTrigger key={tab.key} value={tab.key} className="gap-1.5">
                  <tab.icon className="h-3.5 w-3.5" />
                  {tab.label}
                </TabsTrigger>
              ))}
            </TabsList>
          </div>
        </div>

        {FACULTY_SUBJECT_TABS.map((tab) => (
          <TabsContent key={tab.key} value={tab.key}>
            <tab.Component ctx={ctx} onNavigateTab={setActiveTab} />
          </TabsContent>
        ))}
      </Tabs>
    </PageShell>
  )
}
