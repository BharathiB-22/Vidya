import { useQuery } from '@tanstack/react-query'
import * as api from '@/lib/api/examAnalytics'
import type { AnalyticsParams } from '@/types/examAnalytics'

export const examAnalyticsKeys = {
  all:         ['examAnalytics'] as const,
  scope:       (p?: AnalyticsParams) => [...examAnalyticsKeys.all, p] as const,
  overview:    (p?: AnalyticsParams) => [...examAnalyticsKeys.scope(p), 'overview'] as const,
  subjects:    (p?: AnalyticsParams) => [...examAnalyticsKeys.scope(p), 'subjects'] as const,
  grades:      (p?: AnalyticsParams) => [...examAnalyticsKeys.scope(p), 'grades'] as const,
  batches:     (p?: AnalyticsParams) => [...examAnalyticsKeys.scope(p), 'batches'] as const,
  faculty:     (p?: AnalyticsParams) => [...examAnalyticsKeys.scope(p), 'faculty'] as const,
  revaluation: (p?: AnalyticsParams) => [...examAnalyticsKeys.scope(p), 'revaluation'] as const,
  moderation:  (p?: AnalyticsParams) => [...examAnalyticsKeys.scope(p), 'moderation'] as const,
  dashboard:   (p?: AnalyticsParams) => [...examAnalyticsKeys.scope(p), 'dashboard'] as const,
}

export function useExamDashboard(params?: AnalyticsParams) {
  return useQuery({
    queryKey: examAnalyticsKeys.dashboard(params),
    queryFn:  () => api.getDashboard(params),
  })
}

export function useExamOverview(params?: AnalyticsParams) {
  return useQuery({
    queryKey: examAnalyticsKeys.overview(params),
    queryFn:  () => api.getOverview(params),
  })
}

export function useExamSubjects(params?: AnalyticsParams) {
  return useQuery({
    queryKey: examAnalyticsKeys.subjects(params),
    queryFn:  () => api.getSubjects(params),
  })
}

export function useExamGrades(params?: AnalyticsParams) {
  return useQuery({
    queryKey: examAnalyticsKeys.grades(params),
    queryFn:  () => api.getGrades(params),
  })
}

export function useExamBatches(params?: AnalyticsParams) {
  return useQuery({
    queryKey: examAnalyticsKeys.batches(params),
    queryFn:  () => api.getBatches(params),
  })
}

export function useExamFaculty(params?: AnalyticsParams) {
  return useQuery({
    queryKey: examAnalyticsKeys.faculty(params),
    queryFn:  () => api.getFaculty(params),
  })
}

export function useExamRevaluation(params?: AnalyticsParams) {
  return useQuery({
    queryKey: examAnalyticsKeys.revaluation(params),
    queryFn:  () => api.getRevaluation(params),
  })
}

export function useExamModeration(params?: AnalyticsParams) {
  return useQuery({
    queryKey: examAnalyticsKeys.moderation(params),
    queryFn:  () => api.getModeration(params),
  })
}
