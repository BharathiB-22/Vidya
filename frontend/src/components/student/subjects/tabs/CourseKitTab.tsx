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
            <TabsTrigger value="experiments">Experiments</TabsTrigger>
            <TabsTrigger value="resources">Resources</TabsTrigger>
          </TabsList>

          <TabsContent value="overview">
            <div className="rounded-xl border border-gray-200 bg-white p-4 space-y-3 text-sm">
              <div className="flex items-center gap-2">
                <span
                  className="text-[11px] font-semibold px-2 py-0.5 rounded-full"
                  style={{
                    background: kit.complexity_level === 'PG' ? 'rgba(139,92,246,0.10)' : 'rgba(14,165,233,0.10)',
                    color: kit.complexity_level === 'PG' ? '#7c3aed' : '#0284c7',
                    border: `1px solid ${kit.complexity_level === 'PG' ? 'rgba(139,92,246,0.3)' : 'rgba(14,165,233,0.3)'}`,
                  }}
                >
                  {kit.complexity_level} level
                </span>
                {kit.tone && (
                  <span className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-gray-100 text-gray-600 border border-gray-200">
                    {kit.tone}
                  </span>
                )}
              </div>
              <div className="flex gap-4 flex-wrap text-gray-600">
                <span><span className="text-gray-400">Slides:</span> {kit.slides.length}</span>
                <span><span className="text-gray-400">Assignments:</span> {kit.assignments.length}</span>
              </div>
            </div>
          </TabsContent>

          <TabsContent value="slides">
            <SlideViewer slides={kit.slides} />
          </TabsContent>

          <TabsContent value="experiments">
            {kit.assignments.length === 0 ? (
              <p className="text-sm text-gray-400 py-6 text-center">No activities in this course kit yet.</p>
            ) : (
              <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
                {kit.assignments.map((ka) => (
                  <div key={ka.assignment_number} className="px-5 py-3">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-medium text-gray-800">{ka.title}</span>
                      <span className="text-xs px-1.5 py-0.5 rounded font-medium bg-purple-50 text-purple-700">
                        {ka.assignment_type}
                      </span>
                      {ka.bloom_level && (
                        <span className="text-xs text-gray-400">{ka.bloom_level}</span>
                      )}
                    </div>
                    {ka.question_text && (
                      <p className="text-xs text-gray-500 mt-1 whitespace-pre-wrap">{ka.question_text}</p>
                    )}
                  </div>
                ))}
              </div>
            )}
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
