import { useMutation, useQueryClient } from '@tanstack/react-query'
import * as programsApi from '@/lib/api/programs'
import type { ExportProgramRequest, GenerateProgramRequest, PublishRequest } from '@/types/program'
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

// Phase A: useApproveProgram / useRejectProgram are gone. The Dean cannot
// approve or reject curriculum — see hooks/governance (useSubmitForApproval for
// the Dean, useApproveCurriculum / useReturnCurriculum for governance).

export function usePublishProgram() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: PublishRequest }) =>
      programsApi.publishProgram(id, payload),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: programKeys.status(data.id) })
      qc.invalidateQueries({ queryKey: programKeys.detail(data.id) })
      qc.invalidateQueries({ queryKey: programKeys.all })
      addToast('Program published. It is now read-only and its elective courses are available for offerings.', 'success')
    },
    onError: (err) => {
      addToast(getErrorMessage(err), 'error', 8000)
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
