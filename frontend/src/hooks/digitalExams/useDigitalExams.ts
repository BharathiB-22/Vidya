import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as api from '@/lib/api/digitalExam'
import type { DigitalSessionCreate } from '@/types/digitalExam'

export const digitalExamKeys = {
  all:          ['digitalExams'] as const,
  sessions:     (f?: Record<string, unknown>) => [...digitalExamKeys.all, 'sessions', f] as const,
  session:      (id: string) => [...digitalExamKeys.all, 'sessions', id] as const,
  analytics:    (id: string) => [...digitalExamKeys.all, 'sessions', id, 'analytics'] as const,
  attempt:      (id: string) => [...digitalExamKeys.all, 'attempts', id] as const,
  questions:    (attemptId: string) => [...digitalExamKeys.all, 'attempts', attemptId, 'questions'] as const,
  result:       (attemptId: string) => [...digitalExamKeys.all, 'attempts', attemptId, 'result'] as const,
}

export function useDigitalSessions(params?: { exam_paper_id?: string; offset?: number; limit?: number }) {
  return useQuery({
    queryKey: digitalExamKeys.sessions(params),
    queryFn:  () => api.listSessions(params),
  })
}

export function useDigitalSession(sessionId: string) {
  return useQuery({
    queryKey: digitalExamKeys.session(sessionId),
    queryFn:  () => api.getSession(sessionId),
    enabled:  Boolean(sessionId),
  })
}

export function useAttemptQuestions(attemptId: string) {
  return useQuery({
    queryKey: digitalExamKeys.questions(attemptId),
    queryFn:  () => api.getAttemptQuestions(attemptId),
    enabled:  Boolean(attemptId),
    staleTime: Infinity,
  })
}

export function useAttemptResult(attemptId: string) {
  return useQuery({
    queryKey: digitalExamKeys.result(attemptId),
    queryFn:  () => api.getAttemptResult(attemptId),
    enabled:  Boolean(attemptId),
  })
}

export function useCreateSession() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: DigitalSessionCreate) => api.createSession(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: digitalExamKeys.all }),
  })
}

export function useActivateSession() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (sessionId: string) => api.activateSession(sessionId),
    onSuccess: () => qc.invalidateQueries({ queryKey: digitalExamKeys.all }),
  })
}

export function useCloseSession() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (sessionId: string) => api.closeSession(sessionId),
    onSuccess: () => qc.invalidateQueries({ queryKey: digitalExamKeys.all }),
  })
}

export function useSessionAnalytics(sessionId: string, passThresholdPct = 40) {
  return useQuery({
    queryKey: digitalExamKeys.analytics(sessionId),
    queryFn:  () => api.getSessionAnalytics(sessionId, passThresholdPct),
    enabled:  Boolean(sessionId),
  })
}
