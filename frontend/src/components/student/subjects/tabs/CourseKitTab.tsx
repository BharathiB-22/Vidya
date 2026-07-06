import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Presentation } from 'lucide-react'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import * as courseKitApi from '@/lib/api/courseKit'
import { downloadResource } from '@/hooks/courseKit/useResourceMutations'
import { UnitSelector } from '../UnitSelector'
import { SlideViewer } from '../SlideViewer'
import type { SubjectTabProps } from './types'

export function CourseKitTab({ subject }: SubjectTabProps) {
  const [unit, setUnit] = useState<number | null>(subject.units[0]?.unit_number ?? null)
  const [innerTab, setInnerTab] = useState('overview')

  const { data: kitList, isLoading: isListLoading } = useQuery({
    queryKey: ['student-course-kits', subject.syllabus_id, unit],
    queryFn: () => courseKitApi.studentListKits(subject.syllabus_id!, unit ?? undefined),
    enabled: !!subject.syllabus_id && unit != null,
  })

  const kitSummary = kitList?.items?.[0]

  const { data: kit, isLoading: isKitLoading } = useQuery({
    queryKey: ['student-course-kit', kitSummary?.id],
    queryFn: () => courseKitApi.studentGetKit(kitSummary!.id),
    enabled: !!kitSummary?.id,
  })

  const { data: resources } = useQuery({
    queryKey: ['student-course-kit-resources', kit?.id],
    queryFn: () => courseKitApi.studentListResources(kit!.id),
    enabled: !!kit?.id,
  })

  if (!subject.syllabus_id) {
    return (
      <div className="text-center py-12 rounded-xl border border-dashed border-gray-200">
        <Presentation className="h-8 w-8 mx-auto mb-2 text-gray-200" />
        <p className="text-sm text-gray-400">No approved syllabus yet — course kits aren't available.</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <UnitSelector units={subject.units} selected={unit} onSelect={setUnit} />

      {isListLoading || isKitLoading ? (
        <div className="text-sm text-gray-400 py-8 text-center">Loading course kit…</div>
      ) : !kit ? (
        <div className="text-center py-12 rounded-xl border border-dashed border-gray-200">
          <Presentation className="h-8 w-8 mx-auto mb-2 text-gray-200" />
          <p className="text-sm text-gray-400">No published course kit for this unit yet.</p>
        </div>
      ) : (
        <Tabs value={innerTab} onValueChange={setInnerTab}>
          <TabsList>
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="slides">PPT Slides</TabsTrigger>
            <TabsTrigger value="resources">Resources</TabsTrigger>
          </TabsList>

          <TabsContent value="overview">
            <div className="rounded-xl border border-gray-200 bg-white p-4 space-y-2 text-sm">
              <div className="flex gap-4 flex-wrap text-gray-600">
                <span><span className="text-gray-400">Complexity:</span> {kit.complexity_level}</span>
                {kit.tone && <span><span className="text-gray-400">Tone:</span> {kit.tone}</span>}
                <span><span className="text-gray-400">Slides:</span> {kit.slides.length}</span>
                <span><span className="text-gray-400">Assignments:</span> {kit.assignments.length}</span>
              </div>
            </div>
          </TabsContent>

          <TabsContent value="slides">
            <SlideViewer slides={kit.slides} />
          </TabsContent>

          <TabsContent value="resources">
            {!resources || resources.items.length === 0 ? (
              <p className="text-sm text-gray-400 py-6 text-center">No resources uploaded for this kit yet.</p>
            ) : (
              <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
                {resources.items.map((r) => (
                  <div key={r.id} className="px-5 py-3 flex items-center justify-between gap-4">
                    <div className="min-w-0">
                      <p className="text-sm text-gray-800 truncate">{r.original_filename}</p>
                      <p className="text-xs text-gray-400">{(r.size_bytes / 1024).toFixed(0)} KB</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => downloadResource(kit.id, r.id, r.original_filename)}
                      className="shrink-0 text-xs px-3 py-1.5 rounded-lg border border-gray-200 hover:bg-gray-50 text-gray-700"
                    >
                      Download
                    </button>
                  </div>
                ))}
              </div>
            )}
          </TabsContent>
        </Tabs>
      )}
    </div>
  )
}
