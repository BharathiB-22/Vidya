import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as lpApi from '@/lib/api/learningPackage'
import type { FacultyAddItemPayload, FacultyNoteUploadPayload, LearningPackageListFilters } from '@/types/learningPackage'

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
      const s = query.state.data?.status
      return s === 'PENDING' || s === 'RUNNING' ? 3000 : false
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

// ---------------------------------------------------------------------------
// Faculty curation mutations
// ---------------------------------------------------------------------------

export function useTriggerCuration() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (p: { syllabus_id: string; unit_number: number; top_n?: number }) =>
      lpApi.triggerCuration(p.syllabus_id, p.unit_number, p.top_n),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: learningPackageKeys.detail(data.package_id) })
    },
  })
}

export function useTriggerIndexing() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (packageId: string) => lpApi.triggerIndexing(packageId),
    onSuccess: (_data, packageId) => {
      qc.invalidateQueries({ queryKey: learningPackageKeys.detail(packageId) })
    },
  })
}

export function useAddFacultyItem(packageId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: FacultyAddItemPayload) =>
      lpApi.addFacultyItem(packageId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: learningPackageKeys.items(packageId, false) })
      qc.invalidateQueries({ queryKey: learningPackageKeys.detail(packageId) })
    },
  })
}

export function useRemoveItem(packageId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (itemId: string) => lpApi.removeItem(packageId, itemId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: learningPackageKeys.items(packageId, false) })
      qc.invalidateQueries({ queryKey: learningPackageKeys.detail(packageId) })
    },
  })
}

export function useToggleRecommendation(packageId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ itemId, value }: { itemId: string; value: boolean }) =>
      lpApi.toggleRecommendation(packageId, itemId, value),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: learningPackageKeys.items(packageId, false) })
    },
  })
}

export function useUploadFacultyNote(packageId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: FacultyNoteUploadPayload) =>
      lpApi.uploadFacultyNote(packageId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: learningPackageKeys.items(packageId, false) })
      qc.invalidateQueries({ queryKey: learningPackageKeys.detail(packageId) })
    },
  })
}
