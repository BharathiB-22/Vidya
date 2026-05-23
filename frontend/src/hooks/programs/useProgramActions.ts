import { useMutation, useQueryClient } from '@tanstack/react-query'
import * as programsApi from '@/lib/api/programs'
import type { ApproveRequest, ExportProgramRequest, GenerateProgramRequest, RejectRequest } from '@/types/program'
import { programKeys } from './usePrograms'
import { addToast } from '@/hooks/useToast'
import { getErrorMessage } from '@/lib/api'

export function useGenerateProgram(programId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: GenerateProgramRequest) =>
      programsApi.generateProgram(programId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: programKeys.status(programId) })
      qc.invalidateQueries({ queryKey: programKeys.detail(programId) })
    },
  })
}

export function useApproveProgram() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: ApproveRequest }) =>
      programsApi.approveProgram(id, payload),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: programKeys.status(data.id) })
      qc.invalidateQueries({ queryKey: programKeys.detail(data.id) })
      qc.invalidateQueries({ queryKey: programKeys.all })
      addToast('Program approved successfully.', 'success')
    },
    onError: (err) => {
      addToast(getErrorMessage(err), 'error', 8000)
    },
  })
}

export function useRejectProgram() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: RejectRequest }) =>
      programsApi.rejectProgram(id, payload),
    onSuccess: (_data, { id }) => {
      qc.invalidateQueries({ queryKey: programKeys.status(id) })
      qc.invalidateQueries({ queryKey: programKeys.detail(id) })
      qc.invalidateQueries({ queryKey: programKeys.all })
    },
  })
}

export function useExportProgram() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: ExportProgramRequest }) =>
      programsApi.exportProgram(id, payload),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: programKeys.job(data.program_id, data.job_id) })
    },
  })
}
