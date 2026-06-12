// M09.9 Compliance & Audit — API client
import api from '@/lib/api'
import type {
  AuditTrailResponse,
  ComplianceDashboard,
  ReportResponse,
  ResultChangeHistory,
  TrailParams,
} from '@/types/compliance'

const BASE = '/exam-compliance'

export async function getDashboard(examPaperId?: string): Promise<ComplianceDashboard> {
  const { data } = await api.get(`${BASE}/dashboard`, {
    params: examPaperId ? { exam_paper_id: examPaperId } : undefined,
  })
  return data
}

export async function getResultHistory(scriptId: string): Promise<ResultChangeHistory> {
  const { data } = await api.get(`${BASE}/result-history/${scriptId}`)
  return data
}

export async function listReports(): Promise<string[]> {
  const { data } = await api.get(`${BASE}/reports`)
  return data
}

export async function getReport(report: string, examPaperId?: string): Promise<ReportResponse> {
  const { data } = await api.get(`${BASE}/reports/${report}`, {
    params: examPaperId ? { exam_paper_id: examPaperId } : undefined,
  })
  return data
}

// Authenticated CSV download — fetched as a blob (so Authorization and the
// X-Tenant-Slug header are carried) and saved via a transient object URL.
export async function downloadReportCsv(report: string, examPaperId?: string): Promise<void> {
  const res = await api.get(`${BASE}/reports/${report}/export`, {
    params: examPaperId ? { exam_paper_id: examPaperId } : undefined,
    responseType: 'blob',
  })
  const url = window.URL.createObjectURL(new Blob([res.data], { type: 'text/csv' }))
  const a = document.createElement('a')
  a.href = url
  a.download = `compliance_${report}.csv`
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.URL.revokeObjectURL(url)
}

// Audit trail — one helper per scope, all returning the same shape.
export async function getTrail(
  scope: 'date_range' | 'script' | 'student' | 'evaluator' | 'exam',
  ref: string | undefined,
  params: TrailParams,
): Promise<AuditTrailResponse> {
  const path =
    scope === 'date_range' ? `${BASE}/audit-trail`
      : scope === 'script' ? `${BASE}/audit-trail/script/${ref}`
        : scope === 'student' ? `${BASE}/audit-trail/student/${ref}`
          : scope === 'evaluator' ? `${BASE}/audit-trail/evaluator/${ref}`
            : `${BASE}/audit-trail/exam/${ref}`
  const { data } = await api.get(path, { params })
  return data
}
