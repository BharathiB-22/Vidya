import api from '@/lib/api'
import type {
  LearningPackage,
  LearningPackageListFilters,
  LearningPackageListResponse,
  PackageItem,
  PackageStatus,
} from '@/types/learningPackage'

const BASE = '/learning-packages'

export async function listPackages(
  filters: LearningPackageListFilters,
): Promise<LearningPackageListResponse> {
  const params: Record<string, unknown> = { syllabus_id: filters.syllabus_id }
  if (filters.status)    params.status    = filters.status
  if (filters.page)      params.page      = filters.page
  if (filters.page_size) params.page_size = filters.page_size
  const { data } = await api.get<LearningPackageListResponse>(BASE, { params })
  return data
}

export async function getPackage(id: string): Promise<LearningPackage> {
  const { data } = await api.get<LearningPackage>(`${BASE}/${id}`)
  return data
}

export async function getPackageStatus(id: string): Promise<LearningPackage> {
  const { data } = await api.get<LearningPackage>(`${BASE}/${id}/status`)
  return data
}

export async function listItems(
  packageId: string,
  facultyOnly = false,
): Promise<PackageItem[]> {
  const { data } = await api.get<PackageItem[]>(`${BASE}/${packageId}/items`, {
    params: { faculty_only: facultyOnly },
  })
  return data
}

export async function getJobStatus(jobId: string): Promise<Record<string, unknown>> {
  const { data } = await api.get<Record<string, unknown>>(`${BASE}/jobs/${jobId}`)
  return data
}

// Convenience: list packages filtered to READY status for student browsing.
export async function listReadyPackages(
  syllabusId: string,
): Promise<LearningPackageListResponse> {
  return listPackages({ syllabus_id: syllabusId, status: 'READY' as PackageStatus })
}
