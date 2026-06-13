// M09.7 OCR Review Queue — react-query hooks
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import * as api from '@/lib/api/ocrReview'
import type { QueueListParams } from '@/lib/api/ocrReview'

export const ocrKeys = {
  all:        ['ocrReview'] as const,
  dashboard:  () => [...ocrKeys.all, 'dashboard'] as const,
  thresholds: () => [...ocrKeys.all, 'thresholds'] as const,
  threshold:  (examPaperId?: string) => [...ocrKeys.all, 'threshold', examPaperId] as const,
  queue:      (params?: QueueListParams) => [...ocrKeys.all, 'queue', params] as const,
  detail:     (id: string) => [...ocrKeys.all, 'detail', id] as const,
}

export function useOcrDashboard() {
  return useQuery({
    queryKey: ocrKeys.dashboard(),
    queryFn:  api.getDashboard,
    refetchInterval: 30_000,
  })
}

export function useOcrThreshold(examPaperId?: string) {
  return useQuery({
    queryKey: ocrKeys.threshold(examPaperId),
    queryFn:  () => api.getEffectiveThreshold(examPaperId),
  })
}

export function useAllThresholds() {
  return useQuery({
    queryKey: ocrKeys.thresholds(),
    queryFn:  api.getAllThresholds,
  })
}

export function useOcrQueue(params?: QueueListParams) {
  return useQuery({
    queryKey: ocrKeys.queue(params),
    queryFn:  () => api.listQueue(params),
  })
}

export function useOcrDetail(queueId: string | null) {
  return useQuery({
    queryKey: ocrKeys.detail(queueId ?? ''),
    queryFn:  () => api.getDetail(queueId as string),
    enabled:  !!queueId,
  })
}

// ---- Mutation hooks ---------------------------------------------------------

export function useStartReview() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (queueId: string) => api.startReview(queueId),
    onSuccess: (_data, queueId) => {
      qc.invalidateQueries({ queryKey: ocrKeys.detail(queueId) })
      qc.invalidateQueries({ queryKey: ocrKeys.queue() })
    },
  })
}

export function useAcceptOcr() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ queueId, notes }: { queueId: string; notes?: string }) =>
      api.acceptOcr(queueId, notes),
    onSuccess: (_data, { queueId }) => {
      qc.invalidateQueries({ queryKey: ocrKeys.detail(queueId) })
      qc.invalidateQueries({ queryKey: ocrKeys.queue() })
      qc.invalidateQueries({ queryKey: ocrKeys.dashboard() })
    },
  })
}

export function useCorrectOcr() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ queueId, correctedText, notes }: { queueId: string; correctedText: string; notes?: string }) =>
      api.correctOcr(queueId, correctedText, notes),
    onSuccess: (_data, { queueId }) => {
      qc.invalidateQueries({ queryKey: ocrKeys.detail(queueId) })
      qc.invalidateQueries({ queryKey: ocrKeys.queue() })
      qc.invalidateQueries({ queryKey: ocrKeys.dashboard() })
    },
  })
}

export function useRerunOcr() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ queueId, notes }: { queueId: string; notes?: string }) =>
      api.rerunOcr(queueId, notes),
    onSuccess: (_data, { queueId }) => {
      qc.invalidateQueries({ queryKey: ocrKeys.detail(queueId) })
      qc.invalidateQueries({ queryKey: ocrKeys.queue() })
    },
  })
}

export function useEscalateOcr() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ queueId, notes }: { queueId: string; notes: string }) =>
      api.escalateOcr(queueId, notes),
    onSuccess: (_data, { queueId }) => {
      qc.invalidateQueries({ queryKey: ocrKeys.detail(queueId) })
      qc.invalidateQueries({ queryKey: ocrKeys.queue() })
      qc.invalidateQueries({ queryKey: ocrKeys.dashboard() })
    },
  })
}

export function useMarkUnreadable() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ queueId, notes }: { queueId: string; notes: string }) =>
      api.markUnreadable(queueId, notes),
    onSuccess: (_data, { queueId }) => {
      qc.invalidateQueries({ queryKey: ocrKeys.detail(queueId) })
      qc.invalidateQueries({ queryKey: ocrKeys.queue() })
      qc.invalidateQueries({ queryKey: ocrKeys.dashboard() })
    },
  })
}

export function useSetThreshold() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: api.setThreshold,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ocrKeys.thresholds() })
      qc.invalidateQueries({ queryKey: ocrKeys.threshold() })
    },
  })
}
