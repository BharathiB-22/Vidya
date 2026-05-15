import { useMutation, useQuery } from '@tanstack/react-query'
import * as lpApi from '@/lib/api/learningPackage'
import type { LearningPackageListFilters } from '@/types/learningPackage'

// ---------------------------------------------------------------------------
// Query key factory
// ---------------------------------------------------------------------------

export const learningPackageKeys = {
  all:        ['learning-packages'] as const,
  list:       (f: LearningPackageListFilters) => [...learningPackageKeys.all, 'list', f] as const,
  detail:     (id: string) => [...learningPackageKeys.all, id] as const,
  items:      (id: string, facultyOnly: boolean) =>
    [...learningPackageKeys.all, id, 'items', { facultyOnly }] as const,
  job:        (jobId: string) => [...learningPackageKeys.all, 'jobs', jobId] as const,
  qaSessions: (id: string) => [...learningPackageKeys.all, id, 'qa', 'sessions'] as const,
  qaSession:  (id: string, sid: string) => [...learningPackageKeys.all, id, 'qa', sid] as const,
}

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

export function useLearningPackages(filters: LearningPackageListFilters) {
  return useQuery({
    queryKey: learningPackageKeys.list(filters),
    queryFn:  () => lpApi.listPackages(filters),
    enabled:  Boolean(filters.syllabus_id),
  })
}

export function useLearningPackage(id: string) {
  return useQuery({
    queryKey: learningPackageKeys.detail(id),
    queryFn:  () => lpApi.getPackage(id),
    enabled:  Boolean(id),
  })
}

export function usePackageItems(packageId: string, facultyOnly = false) {
  return useQuery({
    queryKey: learningPackageKeys.items(packageId, facultyOnly),
    queryFn:  () => lpApi.listItems(packageId, facultyOnly),
    enabled:  Boolean(packageId),
  })
}

export function usePackageJob(jobId: string) {
  return useQuery({
    queryKey: learningPackageKeys.job(jobId),
    queryFn:  () => lpApi.getJobStatus(jobId),
    enabled:  Boolean(jobId),
    refetchInterval: (query) => {
      const status = (query.state.data as { status?: string } | undefined)?.status
      return status === 'PENDING' || status === 'RUNNING' ? 3000 : false
    },
  })
}

export function useQASessions(packageId: string) {
  return useQuery({
    queryKey: learningPackageKeys.qaSessions(packageId),
    queryFn:  () => lpApi.listQASessions(packageId),
    enabled:  Boolean(packageId),
  })
}

export function useQASession(packageId: string, sessionId: string) {
  return useQuery({
    queryKey: learningPackageKeys.qaSession(packageId, sessionId),
    queryFn:  () => lpApi.getQASession(packageId, sessionId),
    enabled:  Boolean(packageId) && Boolean(sessionId),
  })
}

export function useAskQuestion(packageId: string) {
  return useMutation({
    mutationFn: ({ question, sessionId }: { question: string; sessionId?: string }) =>
      lpApi.askQuestion(packageId, question, sessionId),
  })
}
