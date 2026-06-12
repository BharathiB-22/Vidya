// M09.9 Compliance & Audit — react-query hooks
import { useQuery } from '@tanstack/react-query'
import * as api from '@/lib/api/compliance'
import type { TrailParams, TrailScope } from '@/types/compliance'

export const complianceKeys = {
  all:        ['compliance'] as const,
  dashboard:  (pid?: string) => [...complianceKeys.all, 'dashboard', pid] as const,
  trail:      (scope: string, ref?: string, params?: TrailParams) =>
    [...complianceKeys.all, 'trail', scope, ref, params] as const,
  result:     (scriptId: string) => [...complianceKeys.all, 'result', scriptId] as const,
  reports:    () => [...complianceKeys.all, 'reports'] as const,
  report:     (report: string, pid?: string) => [...complianceKeys.all, 'report', report, pid] as const,
}

export function useComplianceDashboard(examPaperId?: string) {
  return useQuery({
    queryKey: complianceKeys.dashboard(examPaperId),
    queryFn:  () => api.getDashboard(examPaperId),
  })
}

export function useAuditTrail(
  scope: TrailScope,
  ref: string | undefined,
  params: TrailParams,
  enabled: boolean,
) {
  return useQuery({
    queryKey: complianceKeys.trail(scope, ref, params),
    queryFn:  () => api.getTrail(scope, ref, params),
    enabled,
  })
}

export function useResultHistory(scriptId: string | null) {
  return useQuery({
    queryKey: complianceKeys.result(scriptId ?? ''),
    queryFn:  () => api.getResultHistory(scriptId as string),
    enabled:  !!scriptId,
  })
}

export function useReportNames() {
  return useQuery({
    queryKey: complianceKeys.reports(),
    queryFn:  () => api.listReports(),
  })
}

export function useReport(report: string | null, examPaperId?: string) {
  return useQuery({
    queryKey: complianceKeys.report(report ?? '', examPaperId),
    queryFn:  () => api.getReport(report as string, examPaperId),
    enabled:  !!report,
  })
}
