// M09.8 Examination Analytics — API client
import api from '@/lib/api'
import type {
  AnalyticsParams,
  BatchAnalyticsResponse,
  DashboardResponse,
  FacultyAnalyticsResponse,
  GradeAnalyticsResponse,
  ModerationAnalyticsResponse,
  OverviewResponse,
  RevaluationAnalyticsResponse,
  SubjectAnalyticsResponse,
} from '@/types/examAnalytics'

const BASE = '/exam-analytics'

export async function getOverview(params?: AnalyticsParams): Promise<OverviewResponse> {
  const { data } = await api.get(`${BASE}/overview`, { params })
  return data
}

export async function getSubjects(params?: AnalyticsParams): Promise<SubjectAnalyticsResponse> {
  const { data } = await api.get(`${BASE}/subjects`, { params })
  return data
}

export async function getGrades(params?: AnalyticsParams): Promise<GradeAnalyticsResponse> {
  const { data } = await api.get(`${BASE}/grades`, { params })
  return data
}

export async function getBatches(params?: AnalyticsParams): Promise<BatchAnalyticsResponse> {
  const { data } = await api.get(`${BASE}/batches`, { params })
  return data
}

export async function getFaculty(params?: AnalyticsParams): Promise<FacultyAnalyticsResponse> {
  const { data } = await api.get(`${BASE}/faculty`, { params })
  return data
}

export async function getRevaluation(params?: AnalyticsParams): Promise<RevaluationAnalyticsResponse> {
  const { data } = await api.get(`${BASE}/revaluation`, { params })
  return data
}

export async function getModeration(params?: AnalyticsParams): Promise<ModerationAnalyticsResponse> {
  const { data } = await api.get(`${BASE}/moderation`, { params })
  return data
}

export async function getDashboard(params?: AnalyticsParams): Promise<DashboardResponse> {
  const { data } = await api.get(`${BASE}/dashboard`, { params })
  return data
}
