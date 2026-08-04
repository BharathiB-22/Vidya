import { useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { BookOpen } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { sisApi } from '@/lib/api/sis'
import { SUBJECT_TABS } from '@/components/student/subjects/tabRegistry'

export default function SubjectDetailsPage() {
  const { courseId } = useParams<{ courseId: string }>()
  const [searchParams] = useSearchParams()
  // ?tab=<key> lets other pages deep-link straight to a tab (e.g. the
  // Learning Materials list linking into the Notebook Q&A panel).
  const [activeTab, setActiveTab] = useState(() => {
    const requested = searchParams.get('tab')
    return requested && SUBJECT_TABS.some((t) => t.key === requested)
      ? requested
      : 'overview'
  })

  const { data, isLoading, isError } = useQuery({
    queryKey: ['subject-detail', courseId],
    queryFn: () => sisApi.getSubjectDetail(courseId!),
    enabled: !!courseId,
  })

  if (isLoading) {
    return (
      <PageShell>
        <div className="text-sm text-gray-600 py-16 text-center">Loading subject…</div>
      </PageShell>
    )
  }

  if (isError || !data) {
    return (
      <PageShell>
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          Failed to load this subject. You may not be enrolled, or it may not exist.
        </div>
      </PageShell>
    )
  }

  const visibleTabs = SUBJECT_TABS.filter((tab) => !tab.isVisible || tab.isVisible(data))

  return (
    <PageShell>
      <PageHeader
        icon={BookOpen}
        title={`${data.course_code} — ${data.course_title}`}
        subtitle={`${data.credits} credits · Semester ${data.semester} · Section ${data.section_name}`}
      />

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <div className="overflow-x-auto pb-1">
          <TabsList className="w-max">
            {visibleTabs.map((tab) => (
              <TabsTrigger key={tab.key} value={tab.key} className="gap-1.5">
                <tab.icon className="h-3.5 w-3.5" />
                {tab.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>

        {visibleTabs.map((tab) => (
          <TabsContent key={tab.key} value={tab.key}>
            <tab.Component subject={data} onNavigateTab={setActiveTab} />
          </TabsContent>
        ))}
      </Tabs>
    </PageShell>
  )
}
