import { useMutation, useQueryClient } from '@tanstack/react-query'
import * as programsApi from '@/lib/api/programs'
import type { ElectiveBasketCreate, ElectiveBasketUpdate } from '@/types/program'
import { programKeys } from './usePrograms'

export function useCreateBasket(programId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: ElectiveBasketCreate) => programsApi.createBasket(programId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: programKeys.baskets(programId) })
    },
  })
}

export function useUpdateBasket(programId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ basketId, payload }: { basketId: string; payload: ElectiveBasketUpdate }) =>
      programsApi.updateBasket(programId, basketId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: programKeys.baskets(programId) })
    },
  })
}

export function useDeleteBasket(programId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (basketId: string) => programsApi.deleteBasket(programId, basketId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: programKeys.baskets(programId) })
      qc.invalidateQueries({ queryKey: programKeys.courses(programId) })
    },
  })
}

export function useRemoveCourseFromBasket(programId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (courseId: string) => programsApi.removeCourseFromBasket(programId, courseId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: programKeys.courses(programId) })
      qc.invalidateQueries({ queryKey: programKeys.baskets(programId) })
    },
  })
}
