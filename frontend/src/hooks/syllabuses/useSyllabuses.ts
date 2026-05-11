import { useQuery } from '@tanstack/react-query'
import * as syllabusesApi from '@/lib/api/syllabuses'
import type { ReferenceSearchRequest, SyllabusListFilters } from '@/types/syllabus'

// ---------------------------------------------------------------------------
// Query key factory
// All cache invalidations import this — never hard-code key arrays elsewhere.
// ---------------------------------------------------------------------------

export const syllabusKeys = {
  all:        ['syllabuses'] as const,
  list:       (f: SyllabusListFilters) => [...syllabusKeys.all, 'list', f] as const,
  detail:     (id: string) => [...syllabusKeys.all, id] as const,
  status:     (id: string) => [...syllabusKeys.all, id, 'status'] as const,
  versions:   (id: string) => [...syllabusKeys.all, id, 'versions'] as const,
  compliance: (id: string) => [...syllabusKeys.all, id, 'compliance'] as const,
  outcomes:   (id: string) => [...syllabusKeys.all, id, 'outcomes'] as const,
  copoMatrix: (id: string) => [...syllabusKeys.all, id, 'copo-matrix'] as const,
  units:      (id: string) => [...syllabusKeys.all, id, 'units'] as const,
  references: (id: string) => [...syllabusKeys.all, id, 'references'] as const,
  refSearch:  (id: string, req: ReferenceSearchRequest) =>
    [...syllabusKeys.all, id, 'references', 'search', req] as const,
  job:        (id: string, jobId: string) => [...syllabusKeys.all, id, 'jobs', jobId] as const,
}

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

export function useSyllabuses(filters: SyllabusListFilters) {
  return useQuery({
    queryKey: syllabusKeys.list(filters),
    queryFn:  () => syllabusesApi.listSyllabuses(filters),
    enabled:  Boolean(filters.course_id),
  })
}

export function useSyllabus(id: string) {
  return useQuery({
    queryKey: syllabusKeys.detail(id),
    queryFn:  () => syllabusesApi.getSyllabus(id),
    enabled:  Boolean(id),
  })
}

export function useSyllabusStatus(id: string) {
  return useQuery({
    queryKey: syllabusKeys.status(id),
    queryFn:  () => syllabusesApi.getSyllabusStatus(id),
    enabled:  Boolean(id),
  })
}

export function useSyllabusVersions(id: string) {
  return useQuery({
    queryKey: syllabusKeys.versions(id),
    queryFn:  () => syllabusesApi.getSyllabusVersions(id),
    enabled:  Boolean(id),
  })
}

export function useSyllabusCompliance(id: string) {
  return useQuery({
    queryKey: syllabusKeys.compliance(id),
    queryFn:  () => syllabusesApi.getSyllabusCompliance(id),
    enabled:  Boolean(id),
  })
}

export function useSyllabusOutcomes(syllabusId: string) {
  return useQuery({
    queryKey: syllabusKeys.outcomes(syllabusId),
    queryFn:  () => syllabusesApi.listOutcomes(syllabusId),
    enabled:  Boolean(syllabusId),
  })
}

export function useCOPOMatrix(syllabusId: string) {
  return useQuery({
    queryKey: syllabusKeys.copoMatrix(syllabusId),
    queryFn:  () => syllabusesApi.getCOPOMatrix(syllabusId),
    enabled:  Boolean(syllabusId),
  })
}

export function useSyllabusUnits(syllabusId: string) {
  return useQuery({
    queryKey: syllabusKeys.units(syllabusId),
    queryFn:  () => syllabusesApi.listUnits(syllabusId),
    enabled:  Boolean(syllabusId),
  })
}

export function useSyllabusReferences(syllabusId: string) {
  return useQuery({
    queryKey: syllabusKeys.references(syllabusId),
    queryFn:  () => syllabusesApi.listReferences(syllabusId),
    enabled:  Boolean(syllabusId),
  })
}

export function useSearchReferences(
  syllabusId: string,
  request: ReferenceSearchRequest | null,
) {
  return useQuery({
    queryKey: syllabusKeys.refSearch(syllabusId, request ?? { query: '' }),
    queryFn:  () => syllabusesApi.searchReferences(syllabusId, request!),
    enabled:  Boolean(syllabusId) && Boolean(request?.query),
    staleTime: 60_000,
  })
}

export function useSyllabusJob(syllabusId: string, jobId: string) {
  return useQuery({
    queryKey: syllabusKeys.job(syllabusId, jobId),
    queryFn:  () => syllabusesApi.getJobStatus(syllabusId, jobId),
    enabled:  Boolean(syllabusId) && Boolean(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'PENDING' || status === 'RUNNING' ? 3000 : false
    },
  })
}
