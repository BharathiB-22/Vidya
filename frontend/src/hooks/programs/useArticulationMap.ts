import { useQuery } from '@tanstack/react-query'
import * as programsApi from '@/lib/api/programs'
import { programKeys } from './usePrograms'
import type { Course } from '@/types/program'

export interface ArticulationEdge {
  fromId: string
  toId: string
}

export interface ArticulationMapData {
  adjacency: Record<string, string[]>
  reverseAdj: Record<string, string[]>
  edges: ArticulationEdge[]
}

export function useArticulationMap(programId: string, courses: Course[]) {
  const courseIds = courses.map(c => c.id)

  return useQuery({
    queryKey: programKeys.allPrereqs(programId, courseIds),
    queryFn: async (): Promise<ArticulationMapData> => {
      const results = await Promise.all(
        courses.map(c => programsApi.getCoursePrerequisites(programId, c.id)),
      )

      const adjacency: Record<string, string[]> = {}
      const reverseAdj: Record<string, string[]> = {}
      const edges: ArticulationEdge[] = []

      courses.forEach(c => {
        adjacency[c.id] = []
        reverseAdj[c.id] = []
      })

      results.forEach((prereqs, idx) => {
        const courseId = courses[idx].id
        prereqs.forEach(p => {
          adjacency[courseId].push(p.prerequisite_course_id)
          if (!reverseAdj[p.prerequisite_course_id]) {
            reverseAdj[p.prerequisite_course_id] = []
          }
          reverseAdj[p.prerequisite_course_id].push(courseId)
          edges.push({ fromId: p.prerequisite_course_id, toId: courseId })
        })
      })

      return { adjacency, reverseAdj, edges }
    },
    enabled: Boolean(programId) && courses.length > 0,
  })
}
