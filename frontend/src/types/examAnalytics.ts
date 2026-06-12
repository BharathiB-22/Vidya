// M09.8 Examination Analytics — shared types (mirror backend analytics_schemas)

export interface OverviewResponse {
  scope: 'INSTITUTION' | 'PAPER'
  exam_paper_id: string | null
  exam_paper_title: string | null
  total_students: number
  appeared: number
  absent: number
  pass_count: number
  fail_count: number
  pass_pct: number | null
  average_pct: number | null
  highest_pct: number | null
  lowest_pct: number | null
  pass_threshold_pct: number
  papers_count: number
}

export interface SubjectStat {
  exam_paper_id: string
  exam_paper_title: string | null
  course_code: string | null
  course_title: string | null
  count: number
  average: number | null
  median: number | null
  highest: number | null
  lowest: number | null
  pass_count: number
  fail_count: number
  pass_pct: number | null
  fail_pct: number | null
}

export interface SubjectAnalyticsResponse {
  pass_threshold_pct: number
  subjects: SubjectStat[]
}

export interface FacultyStat {
  evaluator_id: string
  evaluator_name: string | null
  scripts_evaluated: number
  average_awarded_pct: number | null
  average_awarded_marks: number | null
  avg_turnaround_hours: number | null
}

export interface FacultyAnalyticsResponse {
  institution_avg_awarded_pct: number | null
  faculty: FacultyStat[]
}

export interface BatchStat {
  admission_year: number | null
  label: string
  count: number
  average: number | null
  pass_pct: number | null
  topper_pct: number | null
  topper_user_id: string | null
}

export interface BatchAnalyticsResponse {
  pass_threshold_pct: number
  batches: BatchStat[]
}

export interface GradeBucket {
  grade: string
  count: number
  pct_of_total: number
}

export interface GradeAnalyticsResponse {
  total_scripts: number
  buckets: GradeBucket[]
}

export interface RevaluationAnalyticsResponse {
  total_requests: number
  decided: number
  pending: number
  marks_increased: number
  marks_unchanged: number
  average_increase: number | null
  max_increase: number | null
}

export interface ModerationAnalyticsResponse {
  scripts_moderated: number
  completed: number
  pending: number
  average_variance_pct: number | null
  average_delta: number | null
}

export interface DashboardResponse {
  overview: OverviewResponse
  grades: GradeAnalyticsResponse
  top_subjects: SubjectStat[]
  revaluation: RevaluationAnalyticsResponse
  moderation: ModerationAnalyticsResponse
}

export interface AnalyticsParams {
  exam_paper_id?: string
  pass_threshold_pct?: number
}
