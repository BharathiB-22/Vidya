import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ownershipApi, type FacultyProgramAssignCreate } from '@/lib/api/ownership'

export const ownershipKeys = {
  facultyResponsibilities: () => ['ownership', 'faculty-responsibilities'] as const,
  facultySummary:          () => ['ownership', 'faculty-summary'] as const,
  deanPrograms:            () => ['ownership', 'dean-programs'] as const,
  deanFacultyAssignments:  () => ['ownership', 'dean-faculty-assignments'] as const,
  facultyWorkload:         () => ['ownership', 'faculty-workload'] as const,
  ownershipMatrix:         (ids?: string[]) => ['ownership', 'matrix', ids] as const,
  dashboardSummary:        () => ['ownership', 'dashboard-summary'] as const,
}

export function useFacultyResponsibilities() {
  return useQuery({
    queryKey: ownershipKeys.facultyResponsibilities(),
    queryFn:  ownershipApi.getFacultyResponsibilities,
    staleTime: 2 * 60 * 1000,
  })
}

export function useFacultySummary() {
  return useQuery({
    queryKey: ownershipKeys.facultySummary(),
    queryFn:  ownershipApi.getFacultySummary,
    staleTime: 2 * 60 * 1000,
  })
}

export function useDeanPrograms() {
  return useQuery({
    queryKey: ownershipKeys.deanPrograms(),
    queryFn:  ownershipApi.getDeanPrograms,
    staleTime: 2 * 60 * 1000,
  })
}

export function useDeanFacultyAssignments() {
  return useQuery({
    queryKey: ownershipKeys.deanFacultyAssignments(),
    queryFn:  ownershipApi.getDeanFacultyAssignments,
    staleTime: 2 * 60 * 1000,
  })
}

export function useFacultyWorkload() {
  return useQuery({
    queryKey: ownershipKeys.facultyWorkload(),
    queryFn:  ownershipApi.getFacultyWorkload,
    staleTime: 2 * 60 * 1000,
  })
}

export function useOwnershipMatrix(programIds?: string[]) {
  return useQuery({
    queryKey: ownershipKeys.ownershipMatrix(programIds),
    queryFn:  () => ownershipApi.getOwnershipMatrix(programIds),
    staleTime: 60 * 1000,
  })
}

export function useOwnershipDashboardSummary() {
  return useQuery({
    queryKey: ownershipKeys.dashboardSummary(),
    queryFn:  ownershipApi.getDashboardSummary,
    staleTime: 60 * 1000,
  })
}

export function useAssignFacultyToProgram() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: FacultyProgramAssignCreate) =>
      ownershipApi.assignFacultyToProgram(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ownershipKeys.deanFacultyAssignments() })
      qc.invalidateQueries({ queryKey: ownershipKeys.deanPrograms() })
      qc.invalidateQueries({ queryKey: ownershipKeys.ownershipMatrix() })
      qc.invalidateQueries({ queryKey: ownershipKeys.facultyWorkload() })
    },
  })
}

export function useRemoveFacultyFromProgram() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => ownershipApi.removeFacultyFromProgram(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ownershipKeys.deanFacultyAssignments() })
      qc.invalidateQueries({ queryKey: ownershipKeys.deanPrograms() })
      qc.invalidateQueries({ queryKey: ownershipKeys.ownershipMatrix() })
      qc.invalidateQueries({ queryKey: ownershipKeys.facultyWorkload() })
    },
  })
}
