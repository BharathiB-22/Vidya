import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ChevronLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { ProgramStatusBadge } from '@/components/programs/ProgramStatusBadge'
import { ActionBar } from '@/components/programs/ActionBar'
import { SemesterGrid } from '@/components/programs/SemesterGrid'
import { OutcomesSection } from '@/components/programs/OutcomesSection'
import { ComplianceSection } from '@/components/programs/ComplianceSection'
import { ArticulationMap } from '@/components/programs/ArticulationMap'
import { ApprovalPanel } from '@/components/programs/ApprovalPanel'
import { programKeys, useProgramCourses } from '@/hooks/programs'
import { PageLoading } from '@/components/shared/PageLoading'
import { PageError } from '@/components/shared/PageError'
import * as programsApi from '@/lib/api/programs'
import { academicsApi } from '@/lib/api/academics'

export default function ProgramDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const { data: program, isLoading } = useQuery({
    queryKey: programKeys.detail(id!),
    queryFn: () => programsApi.getProgram(id!),
    enabled: Boolean(id),
    refetchInterval: (query) =>
      query.state.data?.status === 'AI_GENERATING' ? 3000 : false,
  })

  const { data: courses = [] } = useProgramCourses(id!)

  const { data: linkedAcadProgram } = useQuery({
    queryKey: ['acad-program', program?.acad_program_id],
    queryFn: () => academicsApi.getProgram(program!.acad_program_id!),
    enabled: Boolean(program?.acad_program_id),
  })

  if (isLoading) {
    return <div className="p-6"><PageLoading message="Loading program…" /></div>
  }

  if (!program) {
    return <div className="p-6"><PageError message="Program not found or you don't have access." /></div>
  }

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      {/* Back + header */}
      <div className="mb-6">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => navigate('/programs')}
          className="mb-3 -ml-1"
        >
          <ChevronLeft className="h-4 w-4 mr-1" />
          Programs
        </Button>
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{program.title}</h1>
            <div className="flex items-center gap-2 mt-1 text-sm text-gray-500 flex-wrap">
              <span>{program.department}</span>
              <span className="text-gray-300">·</span>
              <span>{program.degree_type}</span>
              <span className="text-gray-300">·</span>
              <span>{program.duration_years} yr / {program.total_credits} cr</span>
              <span className="text-gray-300">·</span>
              <span>v{program.version}</span>
              {linkedAcadProgram && (
                <>
                  <span className="text-gray-300">·</span>
                  <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-indigo-50 text-indigo-700 border border-indigo-100">
                    {linkedAcadProgram.name} ({linkedAcadProgram.code})
                  </span>
                </>
              )}
            </div>
          </div>
          <ProgramStatusBadge status={program.status} />
        </div>
      </div>

      {/* Action bar */}
      <ActionBar program={program} />

      {/* Content tabs */}
      <Tabs defaultValue="structure" className="mt-6">
        <TabsList>
          <TabsTrigger value="structure">Structure</TabsTrigger>
          <TabsTrigger value="outcomes">Outcomes</TabsTrigger>
          <TabsTrigger value="compliance">Compliance</TabsTrigger>
          <TabsTrigger value="map">Map</TabsTrigger>
          <TabsTrigger value="approval">Approval</TabsTrigger>
        </TabsList>

        <TabsContent value="structure" className="mt-4">
          <SemesterGrid program={program} courses={courses} />
        </TabsContent>

        <TabsContent value="outcomes" className="mt-4">
          <OutcomesSection program={program} />
        </TabsContent>

        <TabsContent value="compliance" className="mt-4">
          <ComplianceSection program={program} />
        </TabsContent>

        <TabsContent value="map" className="mt-4">
          <ArticulationMap program={program} courses={courses} />
        </TabsContent>

        <TabsContent value="approval" className="mt-4">
          <ApprovalPanel program={program} linkedAcadProgram={linkedAcadProgram} />
        </TabsContent>
      </Tabs>
    </div>
  )
}
