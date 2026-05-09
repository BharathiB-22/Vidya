import { useMutation, useQueryClient } from '@tanstack/react-query'
import * as programsApi from '@/lib/api/programs'
import type { ProgramCreate, ProgramUpdate } from '@/types/program'
import { programKeys } from './usePrograms'

export function useCreateProgram() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: ProgramCreate) => programsApi.createProgram(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: programKeys.all })
    },
  })
}

export function useUpdateProgram() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: ProgramUpdate }) =>
      programsApi.updateProgram(id, payload),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: programKeys.detail(data.id) })
      qc.invalidateQueries({ queryKey: programKeys.all })
    },
  })
}

export function useDeleteProgram() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => programsApi.deleteProgram(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: programKeys.all })
    },
  })
}

export function useForkProgram() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => programsApi.forkProgram(id),
    onSuccess: (forked) => {
      qc.invalidateQueries({ queryKey: programKeys.all })
      // Pre-populate the forked program's detail cache immediately
      qc.setQueryData(programKeys.detail(forked.id), forked)
    },
  })
}
