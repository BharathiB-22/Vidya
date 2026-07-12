import { useMutation, useQueryClient } from '@tanstack/react-query'
import * as programsApi from '@/lib/api/programs'
import type { ElectiveBasketCreate, ElectiveBasketUpdate, ElectiveChoiceCreate } from '@/types/program'
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

// ---------------------------------------------------------------------------
// Slot choices + lifecycle. Adding a choice creates a real course, so the
// program's course list is invalidated alongside the baskets.
// ---------------------------------------------------------------------------

function invalidateSlotAndCourses(qc: ReturnType<typeof useQueryClient>, programId: string) {
  qc.invalidateQueries({ queryKey: programKeys.baskets(programId) })
  qc.invalidateQueries({ queryKey: programKeys.courses(programId) })
}

export function useAddElectiveChoice(programId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ basketId, payload }: { basketId: string; payload: ElectiveChoiceCreate }) =>
      programsApi.addElectiveChoice(programId, basketId, payload),
    onSuccess: () => invalidateSlotAndCourses(qc, programId),
  })
}

export function useRemoveElectiveChoice(programId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ basketId, courseId }: { basketId: string; courseId: string }) =>
      programsApi.removeElectiveChoice(programId, basketId, courseId),
    onSuccess: () => invalidateSlotAndCourses(qc, programId),
  })
}

export function usePublishElectiveSlot(programId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (basketId: string) => programsApi.publishElectiveSlot(programId, basketId),
    onSuccess: () => invalidateSlotAndCourses(qc, programId),
  })
}

export function useOpenElectiveRegistration(programId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (basketId: string) => programsApi.openElectiveRegistration(programId, basketId),
    onSuccess: () => invalidateSlotAndCourses(qc, programId),
  })
}

export function useCloseElectiveRegistration(programId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (basketId: string) => programsApi.closeElectiveRegistration(programId, basketId),
    onSuccess: () => invalidateSlotAndCourses(qc, programId),
  })
}
