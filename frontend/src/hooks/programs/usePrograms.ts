import { useQuery } from '@tanstack/react-query'
import * as programsApi from '@/lib/api/programs'
import type { ProgramListFilters } from '@/types/program'

// ---------------------------------------------------------------------------
// Query key factory
// All cache invalidations import this — never hard-code key arrays elsewhere.
// ---------------------------------------------------------------------------

export const programKeys = {
  all:         ['programs'] as const,
  list:        (f?: ProgramListFilters) => [...programKeys.all, 'list', f] as const,
  detail:      (id: string) => [...programKeys.all, id] as const,
  status:      (id: string) => [...programKeys.all, id, 'status'] as const,
  versions:    (id: string) => [...programKeys.all, id, 'versions'] as const,
  outcomes:    (id: string) => [...programKeys.all, id, 'outcomes'] as const,
  courses:     (id: string) => [...programKeys.all, id, 'courses'] as const,
  baskets:     (id: string) => [...programKeys.all, id, 'electives', 'baskets'] as const,
  prereqs:     (id: string, courseId: string) => [...programKeys.all, id, 'courses', courseId, 'prerequisites'] as const,
  allPrereqs:  (id: string, courseIds: string[]) => [...programKeys.all, id, 'all-prereqs', courseIds] as const,
  compliance:  (id: string) => [...programKeys.all, id, 'compliance'] as const,
  job:         (id: string, jobId: string) => [...programKeys.all, id, 'jobs', jobId] as const,
}

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

export function usePrograms(filters?: ProgramListFilters) {
  return useQuery({
    queryKey: programKeys.list(filters),
    queryFn:  () => programsApi.listPrograms(filters),
  })
}

export function useProgram(id: string) {
  return useQuery({
    queryKey: programKeys.detail(id),
    queryFn:  () => programsApi.getProgram(id),
    enabled:  Boolean(id),
  })
}

export function useProgramStatus(id: string) {
  return useQuery({
    queryKey: programKeys.status(id),
    queryFn:  () => programsApi.getProgramStatus(id),
    enabled:  Boolean(id),
  })
}

export function useProgramVersions(id: string) {
  return useQuery({
    queryKey: programKeys.versions(id),
    queryFn:  () => programsApi.getProgramVersions(id),
    enabled:  Boolean(id),
  })
}

export function useProgramOutcomes(programId: string) {
  return useQuery({
    queryKey: programKeys.outcomes(programId),
    queryFn:  () => programsApi.listOutcomes(programId),
    enabled:  Boolean(programId),
  })
}

export function useProgramCourses(programId: string) {
  return useQuery({
    queryKey: programKeys.courses(programId),
    queryFn:  () => programsApi.listCourses(programId),
    enabled:  Boolean(programId),
  })
}

export function useElectiveBaskets(programId: string) {
  return useQuery({
    queryKey: programKeys.baskets(programId),
    queryFn:  () => programsApi.listBaskets(programId),
    enabled:  Boolean(programId),
  })
}

export function useCoursePrerequisites(programId: string, courseId: string) {
  return useQuery({
    queryKey: programKeys.prereqs(programId, courseId),
    queryFn:  () => programsApi.getCoursePrerequisites(programId, courseId),
    enabled:  Boolean(programId) && Boolean(courseId),
  })
}

export function useProgramCompliance(programId: string) {
  return useQuery({
    queryKey: programKeys.compliance(programId),
    queryFn:  () => programsApi.getCompliance(programId),
    enabled:  Boolean(programId),
  })
}

export function useJobStatus(programId: string, jobId: string) {
  return useQuery({
    queryKey: programKeys.job(programId, jobId),
    queryFn:  () => programsApi.getJobStatus(programId, jobId),
    enabled:  Boolean(programId) && Boolean(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'PENDING' || status === 'RUNNING' ? 3000 : false
    },
  })
}
