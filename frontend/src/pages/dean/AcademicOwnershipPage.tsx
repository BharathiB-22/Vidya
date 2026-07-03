import { LayoutGrid } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import DashboardTab from '@/pages/dean/academicOwnership/DashboardTab'
import ProgramOwnershipTab from '@/pages/dean/academicOwnership/ProgramOwnershipTab'
import CourseOwnershipTab from '@/pages/dean/academicOwnership/CourseOwnershipTab'
import OwnershipReportTab from '@/pages/dean/academicOwnership/OwnershipReportTab'

export default function AcademicOwnershipPage() {
  return (
    <PageShell>
      <PageHeader
        title="Academic Ownership"
        subtitle="Assign faculty, govern programs, and report on teaching coverage — all in one place."
        icon={LayoutGrid}
      />

      <Tabs defaultValue="dashboard">
        <TabsList>
          <TabsTrigger value="dashboard">Dashboard</TabsTrigger>
          <TabsTrigger value="program-ownership">Program Ownership</TabsTrigger>
          <TabsTrigger value="course-ownership">Course Ownership</TabsTrigger>
          <TabsTrigger value="ownership-report">Ownership Report</TabsTrigger>
        </TabsList>

        <TabsContent value="dashboard">
          <DashboardTab />
        </TabsContent>
        <TabsContent value="program-ownership">
          <ProgramOwnershipTab />
        </TabsContent>
        <TabsContent value="course-ownership">
          <CourseOwnershipTab />
        </TabsContent>
        <TabsContent value="ownership-report">
          <OwnershipReportTab />
        </TabsContent>
      </Tabs>
    </PageShell>
  )
}
