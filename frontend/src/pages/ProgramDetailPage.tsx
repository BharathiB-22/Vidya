import { useEffect, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
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
import { ElectiveBasketsSection } from '@/components/programs/ElectiveBasketsSection'
import { programKeys, useProgramCourses } from '@/hooks/programs'
import { PageLoading } from '@/components/shared/PageLoading'
import { PageError } from '@/components/shared/PageError'
import * as programsApi from '@/lib/api/programs'
import { academicsApi } from '@/lib/api/academics'

export default function ProgramDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()

  // Controlled, so the submission checklist can jump the Dean straight to the tab
  // that holds whatever is missing.
  const [tab, setTab] = useState('structure')

  const { data: program, isLoading } = useQuery({
    queryKey: programKeys.detail(id!),
    queryFn: () => programsApi.getProgram(id!),
    enabled: Boolean(id),
    refetchInterval: (query) =>
      query.state.data?.status === 'AI_GENERATING' ? 3000 : false,
  })

  const { data: courses = [] } = useProgramCourses(id!)

  // When generation finishes (AI_GENERATING → any other status), the program
  // detail cache is already fresh from polling, but courses/outcomes/compliance
  // are separate cache entries that were never invalidated. Force-refresh them
  // so the Structure, Outcomes, and Compliance tabs update without Ctrl+R.
  const prevStatusRef = useRef<string | undefined>(undefined)
  useEffect(() => {
    const prev = prevStatusRef.current
    const curr = program?.status
    prevStatusRef.current = curr
    if (prev === 'AI_GENERATING' && curr && curr !== 'AI_GENERATING') {
      qc.invalidateQueries({ queryKey: programKeys.courses(id!) })
      qc.invalidateQueries({ queryKey: programKeys.outcomes(id!) })
      qc.invalidateQueries({ queryKey: programKeys.compliance(id!) })
    }
  }, [program?.status, id, qc])

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
            {program.ai_instructions && (
              <div className="mt-2 max-w-2xl rounded-md bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-amber-800">
                <span className="font-semibold">AI Instructions: </span>
                {program.ai_instructions}
              </div>
            )}
          </div>
          <ProgramStatusBadge status={program.status} />
        </div>
      </div>

      {/* Action bar.
          `onNavigateToSection` lets the submission checklist take the Dean straight
          to whatever is missing — a list of failures you then have to go and find
          yourself is only half an answer. */}
      <ActionBar program={program} onNavigateToSection={setTab} />

      {/* Content tabs */}
      <Tabs value={tab} onValueChange={setTab} className="mt-6">
        <TabsList>
          <TabsTrigger value="structure">Structure</TabsTrigger>
          <TabsTrigger value="electives">Elective Basket</TabsTrigger>
          <TabsTrigger value="outcomes">Outcomes</TabsTrigger>
          <TabsTrigger value="compliance">Compliance</TabsTrigger>
          <TabsTrigger value="map">Map</TabsTrigger>
          <TabsTrigger value="approval">Approval</TabsTrigger>
        </TabsList>

        <TabsContent value="structure" className="mt-4">
          <SemesterGrid program={program} courses={courses} />
        </TabsContent>

        <TabsContent value="electives" className="mt-4">
          <ElectiveBasketsSection program={program} />
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
