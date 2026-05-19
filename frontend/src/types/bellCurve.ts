// M10 Bell Curve Normaliser — TypeScript types

export type AnalysisStatus =
  | 'PENDING'
  | 'ANALYSING'
  | 'READY'
  | 'BOARD_REVIEWED'
  | 'APPLIED'
  | 'NO_ACTION'
  | 'FAILED'

export type BoardDecision =
  | 'ACCEPTED_SUGGESTION'
  | 'MODIFIED'
  | 'REJECTED'

export type NormalisationMethod =
  | 'LINEAR_SCALE'
  | 'PERCENTILE_MAP'
  | 'BOUNDARY_SHIFT'
  | 'NONE'
  | 'CUSTOM'

// ---------------------------------------------------------------------------
// Sub-models
// ---------------------------------------------------------------------------

export interface HistogramBin {
  bin_start: number
  bin_end:   number
  count:     number
}

export interface RawStats {
  mean:      number
  std:       number
  median:    number
  min:       number
  max:       number
  skewness:  number
  kurtosis:  number
  q1:        number
  q3:        number
  histogram: HistogramBin[]
}

export interface AnomalyItem {
  type:           string
  severity:       'WARNING' | 'CRITICAL'
  description:    string
  threshold:      number
  observed_value: number
}

export interface CrossEvaluatorStat {
  evaluator_id: string
  mean:         number
  std:          number
  count:        number
  z_score:      number
  is_outlier:   boolean
}

export interface ProjectedStats {
  mean:     number
  std:      number
  median:   number
  min:      number
  max:      number
  skewness: number
}

export interface NormalisationSuggestion {
  method:          NormalisationMethod
  params:          Record<string, unknown>
  reasoning:       string
  projected_stats: ProjectedStats | null
}

// ---------------------------------------------------------------------------
// Analysis
// ---------------------------------------------------------------------------

export interface BellCurveAnalysis {
  id:                       string
  exam_paper_id:            string
  analysis_job_id:          string | null
  score_count:              number | null
  raw_stats:                RawStats | null
  anomalies:                AnomalyItem[] | null
  normalisation_suggestion: NormalisationSuggestion | null
  cross_evaluator_stats:    CrossEvaluatorStat[] | null
  triggered_by:             string
  status:                   AnalysisStatus
  triggered_at:             string | null
  analysis_completed_at:    string | null
  created_at:               string
}

export interface BellCurveAnalysisListResponse {
  items:  BellCurveAnalysis[]
  total:  number
  offset: number
  limit:  number
}

// ---------------------------------------------------------------------------
// Decision
// ---------------------------------------------------------------------------

export interface BellCurveDecision {
  id:                   string
  analysis_id:          string
  exam_paper_id:        string
  decision:             BoardDecision
  normalisation_method: NormalisationMethod
  normalisation_params: Record<string, unknown>
  projected_stats:      ProjectedStats | null
  ratified_by:          string
  ratification_note:    string | null
  ratified_at:          string
}

export interface BellCurveDecisionListResponse {
  items:  BellCurveDecision[]
  total:  number
  offset: number
  limit:  number
}

// ---------------------------------------------------------------------------
// Normalised scores (ledger)
// ---------------------------------------------------------------------------

export interface NormalisedScore {
  id:                   string
  decision_id:          string
  analysis_id:          string
  exam_paper_id:        string
  student_user_id:      string | null
  student_roll_ref:     string | null
  raw_score:            number
  normalised_score:     number
  max_marks:            number
  normalisation_method: string
  created_at:           string
}

export interface NormalisedScoreListResponse {
  items:  NormalisedScore[]
  total:  number
  offset: number
  limit:  number
}

// ---------------------------------------------------------------------------
// Request/Response types
// ---------------------------------------------------------------------------

export interface TriggerAnalysisRequest {
  exam_paper_id: string
}

export interface TriggerAnalysisResponse {
  analysis_id: string
  job_id:      string
  status:      AnalysisStatus
}

export interface PreviewNormalisationRequest {
  method: NormalisationMethod
  params: Record<string, unknown>
}

export interface PreviewNormalisationResponse {
  method:          NormalisationMethod
  params:          Record<string, unknown>
  projected_stats: ProjectedStats
  score_deltas:    Array<{ student_roll_ref: string; raw: number; normalised: number }>
}

export interface RatifyRequest {
  decision:              BoardDecision
  normalisation_method:  NormalisationMethod
  normalisation_params:  Record<string, unknown>
  ratification_note?:    string
}

export interface RatifyResponse {
  analysis_id:    string
  decision_id:    string
  decision:       BoardDecision
  method:         NormalisationMethod
  scores_written: number
}

export interface JobStatusResponse {
  analysis_id:  string
  job_id:       string | null
  status:       string
  started_at:   string | null
  completed_at: string | null
  error:        string | null
}
