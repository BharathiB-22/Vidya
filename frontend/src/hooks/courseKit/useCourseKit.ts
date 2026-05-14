import { useQuery } from '@tanstack/react-query'
import * as courseKitApi from '@/lib/api/courseKit'
import type { CourseKitListFilters } from '@/types/courseKit'

// ---------------------------------------------------------------------------
// Query key factory
// All cache invalidations import this — never hard-code key arrays elsewhere.
// ---------------------------------------------------------------------------

export const courseKitKeys = {
  all:        ['course-kits'] as const,
  list:       (f: CourseKitListFilters) => [...courseKitKeys.all, 'list', f] as const,
  detail:     (id: string) => [...courseKitKeys.all, id] as const,
  status:     (id: string) => [...courseKitKeys.all, id, 'status'] as const,
  versions:   (id: string) => [...courseKitKeys.all, id, 'versions'] as const,
  compliance: (id: string) => [...courseKitKeys.all, id, 'compliance'] as const,
  slides:     (id: string) => [...courseKitKeys.all, id, 'slides'] as const,
  quizlets:   (id: string) => [...courseKitKeys.all, id, 'quizlets'] as const,
  assignments:(id: string) => [...courseKitKeys.all, id, 'assignments'] as const,
  exports:    (id: string) => [...courseKitKeys.all, id, 'exports'] as const,
  job:        (id: string, jobId: string) => [...courseKitKeys.all, id, 'jobs', jobId] as const,
}

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

export function useCourseKits(filters: CourseKitListFilters) {
  return useQuery({
    queryKey: courseKitKeys.list(filters),
    queryFn:  () => courseKitApi.listKits(filters),
    enabled:  Boolean(filters.syllabus_id),
  })
}

export function useCourseKit(id: string) {
  return useQuery({
    queryKey: courseKitKeys.detail(id),
    queryFn:  () => courseKitApi.getKit(id),
    enabled:  Boolean(id),
  })
}

export function useCourseKitStatus(id: string) {
  return useQuery({
    queryKey: courseKitKeys.status(id),
    queryFn:  () => courseKitApi.getKitStatus(id),
    enabled:  Boolean(id),
  })
}

export function useCourseKitVersions(id: string) {
  return useQuery({
    queryKey: courseKitKeys.versions(id),
    queryFn:  () => courseKitApi.listVersions(id),
    enabled:  Boolean(id),
  })
}

export function useCourseKitCompliance(id: string) {
  return useQuery({
    queryKey: courseKitKeys.compliance(id),
    queryFn:  () => courseKitApi.getKitCompliance(id),
    enabled:  Boolean(id),
  })
}

export function useKitSlides(kitId: string) {
  return useQuery({
    queryKey: courseKitKeys.slides(kitId),
    queryFn:  () => courseKitApi.listSlides(kitId),
    enabled:  Boolean(kitId),
  })
}

export function useKitQuizlets(kitId: string) {
  return useQuery({
    queryKey: courseKitKeys.quizlets(kitId),
    queryFn:  () => courseKitApi.listQuizlets(kitId),
    enabled:  Boolean(kitId),
  })
}

export function useKitAssignments(kitId: string) {
  return useQuery({
    queryKey: courseKitKeys.assignments(kitId),
    queryFn:  () => courseKitApi.listAssignments(kitId),
    enabled:  Boolean(kitId),
  })
}

export function useKitExports(kitId: string) {
  return useQuery({
    queryKey: courseKitKeys.exports(kitId),
    queryFn:  () => courseKitApi.listExports(kitId),
    enabled:  Boolean(kitId),
  })
}

export function useCourseKitJob(kitId: string, jobId: string) {
  return useQuery({
    queryKey: courseKitKeys.job(kitId, jobId),
    queryFn:  () => courseKitApi.getJobStatus(kitId, jobId),
    enabled:  Boolean(kitId) && Boolean(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'PENDING' || status === 'RUNNING' ? 3000 : false
    },
  })
}
