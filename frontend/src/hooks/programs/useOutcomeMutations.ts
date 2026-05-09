import { useMutation, useQueryClient } from '@tanstack/react-query'
import * as programsApi from '@/lib/api/programs'
import type { ProgramOutcome, ProgramOutcomeCreate, ProgramOutcomeUpdate } from '@/types/program'
import { programKeys } from './usePrograms'

export function useAddOutcome(programId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: ProgramOutcomeCreate) => programsApi.addOutcome(programId, payload),
    onMutate: async (payload) => {
      await qc.cancelQueries({ queryKey: programKeys.outcomes(programId) })
      const prev = qc.getQueryData<ProgramOutcome[]>(programKeys.outcomes(programId))
      qc.setQueryData<ProgramOutcome[]>(programKeys.outcomes(programId), (old) => [
        ...(old ?? []),
        {
          id: `optimistic-${Date.now()}`,
          program_id: programId,
          code: payload.code,
          description: payload.description,
          bloom_level: payload.bloom_level ?? null,
          display_order: payload.display_order ?? (old?.length ?? 0) + 1,
          created_at: new Date().toISOString(),
        },
      ])
      return { prev }
    },
    onError: (_err, _vars, context) => {
      if (context?.prev !== undefined) {
        qc.setQueryData(programKeys.outcomes(programId), context.prev)
      }
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: programKeys.outcomes(programId) })
    },
  })
}

export function useUpdateOutcome(programId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ outcomeId, payload }: { outcomeId: string; payload: ProgramOutcomeUpdate }) =>
      programsApi.updateOutcome(programId, outcomeId, payload),
    onMutate: async ({ outcomeId, payload }) => {
      await qc.cancelQueries({ queryKey: programKeys.outcomes(programId) })
      const prev = qc.getQueryData<ProgramOutcome[]>(programKeys.outcomes(programId))
      qc.setQueryData<ProgramOutcome[]>(programKeys.outcomes(programId), (old) =>
        old?.map((o) => (o.id === outcomeId ? { ...o, ...payload } : o)) ?? [],
      )
      return { prev }
    },
    onError: (_err, _vars, context) => {
      if (context?.prev !== undefined) {
        qc.setQueryData(programKeys.outcomes(programId), context.prev)
      }
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: programKeys.outcomes(programId) })
    },
  })
}

export function useDeleteOutcome(programId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (outcomeId: string) => programsApi.deleteOutcome(programId, outcomeId),
    onMutate: async (outcomeId) => {
      await qc.cancelQueries({ queryKey: programKeys.outcomes(programId) })
      const prev = qc.getQueryData<ProgramOutcome[]>(programKeys.outcomes(programId))
      qc.setQueryData<ProgramOutcome[]>(programKeys.outcomes(programId), (old) =>
        old?.filter((o) => o.id !== outcomeId) ?? [],
      )
      return { prev }
    },
    onError: (_err, _vars, context) => {
      if (context?.prev !== undefined) {
        qc.setQueryData(programKeys.outcomes(programId), context.prev)
      }
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: programKeys.outcomes(programId) })
    },
  })
}
