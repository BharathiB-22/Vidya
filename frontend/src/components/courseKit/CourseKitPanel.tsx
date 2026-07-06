import { useState } from 'react'
import { Loader2, AlertTriangle, Archive } from 'lucide-react'
import { CourseKitStatusBadge } from '@/components/courseKit/CourseKitStatusBadge'
import { CourseKitActionBar } from '@/components/courseKit/CourseKitActionBar'
import { SlidesSection } from '@/components/courseKit/SlidesSection'
import { AssignmentsSection } from '@/components/courseKit/AssignmentsSection'
import { ResourcesSection } from '@/components/courseKit/ResourcesSection'
import {
  useCourseKit,
  useKitSlides,
  useKitAssignments,
  useKitResources,
} from '@/hooks/courseKit'
import { useWorkspace } from '@/lib/workspace'

type SubTab = 'slides' | 'assignments' | 'resources'

const WRITE_ROLES = ['ADMIN', 'FACULTY']

export interface CourseKitPanelProps {
  kitId: string
}

/**
 * Composes the SAME exported Course Kit section components used by
 * CourseKitDetailPage.tsx — no duplicated upload/publish logic, just a
 * lighter-weight shell for embedding inside the Faculty Subject Workspace.
 */
export function CourseKitPanel({ kitId }: CourseKitPanelProps) {
  const [subTab, setSubTab] = useState<SubTab>('slides')
  const { activeWorkspace: role } = useWorkspace()
  const isDean = role === 'DEAN'
  const canWrite = WRITE_ROLES.includes(role)

  const { data: kit, isLoading, isError } = useCourseKit(kitId)
  const { data: slides = [], isLoading: slidesLoading } = useKitSlides(kitId)
  const { data: assignments = [], isLoading: assignsLoading } = useKitAssignments(kitId)
  const { data: resourcesData, isLoading: resourcesLoading } = useKitResources(kitId)
  const resources = resourcesData?.items ?? []

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
      </div>
    )
  }

  if (isError || !kit) {
    return (
      <div className="p-6 text-center">
        <AlertTriangle className="h-8 w-8 mx-auto mb-3 text-red-400" />
        <p className="text-sm text-red-600">Failed to load course kit.</p>
      </div>
    )
  }

  const isEditable = kit.status === 'DRAFT' && canWrite
  const isArchived = kit.status === 'ARCHIVED'
  const showSpeakerNotes = !isDean

  const SUB_TABS: Array<{ key: SubTab; label: string; count: number }> = [
    { key: 'slides', label: 'Slides', count: slides.length },
    { key: 'assignments', label: 'Experiments', count: assignments.length },
    { key: 'resources', label: 'Notes & Resources', count: resources.length },
  ]

  return (
    <div className="space-y-4">
      <div className="flex items-start gap-3 flex-wrap">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h2 className="text-lg font-bold text-gray-900">Unit {kit.unit_number} — v{kit.version}</h2>
            <CourseKitStatusBadge status={kit.status} />
            <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full font-medium">
              {kit.complexity_level}
            </span>
          </div>
        </div>
      </div>

      <CourseKitActionBar kit={kit} />

      {isArchived && (
        <div className="flex items-center gap-2 rounded-lg bg-blue-50 border border-blue-200 px-4 py-3 text-blue-700 text-sm">
          <Archive className="h-4 w-4 shrink-0" />
          <span>This kit is <strong>archived</strong> and read-only. Use <strong>Fork</strong> to create a new version.</span>
        </div>
      )}

      <div className="border-b border-gray-200">
        <nav className="flex gap-0 overflow-x-auto" role="tablist">
          {SUB_TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              role="tab"
              aria-selected={subTab === t.key}
              onClick={() => setSubTab(t.key)}
              className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium whitespace-nowrap border-b-2 transition-colors ${
                subTab === t.key
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              {t.label}
              {t.count > 0 && (
                <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full ${
                  subTab === t.key ? 'bg-blue-100 text-blue-600' : 'bg-gray-100 text-gray-500'
                }`}>
                  {t.count}
                </span>
              )}
            </button>
          ))}
        </nav>
      </div>

      <div className="min-h-[16rem]" role="tabpanel">
        {subTab === 'slides' && (
          <SlidesSection
            kitId={kitId}
            slides={slides}
            isEditable={isEditable}
            showSpeakerNotes={showSpeakerNotes}
            isLoading={slidesLoading}
          />
        )}
        {subTab === 'assignments' && (
          <AssignmentsSection
            kitId={kitId}
            assignments={assignments}
            isEditable={isEditable}
            showModelAnswer={!isDean}
            isLoading={assignsLoading}
          />
        )}
        {subTab === 'resources' && (
          <ResourcesSection
            kitId={kitId}
            resources={resources}
            canUpload={canWrite}
            isLoading={resourcesLoading}
          />
        )}
      </div>
    </div>
  )
}
