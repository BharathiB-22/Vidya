// M07 Research Supervision — TypeScript types

export type ProblemSource      = 'STUDENT_PROPOSED' | 'AI_GENERATED'
export type ProblemStatus      = 'DRAFT' | 'PENDING_REVIEW' | 'ACCEPTED' | 'REVISION_REQUESTED' | 'REJECTED'
export type AIRecommendation   = 'ACCEPT' | 'REVISE' | 'REJECT'
export type GuideDecision      = 'ACCEPT' | 'REVISE' | 'REJECT'
export type DocumentStatus     = 'SUBMITTED' | 'EVALUATING' | 'EVALUATED' | 'GUIDE_REVIEWED' | 'APPROVED' | 'REVISION_REQUESTED'
export type VivaStatus         = 'SCHEDULED' | 'IN_PROGRESS' | 'COMPLETED' | 'ASR_PROCESSING' | 'EVALUATED' | 'GUIDE_RATIFIED'

export interface ResearchQuestion {
  question: string
}

export interface ResearchProblem {
  id: string
  guide_user_id: string
  student_user_id: string | null
  title: string
  abstract: string
  research_questions: ResearchQuestion[]
  source: ProblemSource
  novelty_score: number | null
  feasibility_score: number | null
  clarity_score: number | null
  ai_recommendation: AIRecommendation | null
  ai_reasoning: string | null
  ai_model: string | null
  eval_job_id: string | null
  status: ProblemStatus
  guide_decision: GuideDecision | null
  guide_note: string | null
  decided_at: string | null
  created_at: string
  updated_at: string | null
}

export interface ProblemListResponse {
  items: ResearchProblem[]
  total: number
  offset: number
  limit: number
}

export interface ProblemCreate {
  guide_user_id: string
  title: string
  abstract: string
  research_questions: ResearchQuestion[]
}

export interface GuideDecisionRequest {
  decision: GuideDecision
  guide_note?: string
}

// ── Document ─────────────────────────────────────────────────────────────────

export interface FormatIssue {
  section: string
  issue: string
}

export interface PlagiarismMatch {
  submission_id: string
  similarity: number
  student_user_id?: string
}

export interface AiHighlight {
  start: number
  end: number
  score: number
}

export interface AiScanDetail {
  probability: number
  confidence: number
  burstiness_score: number
  repetition_score: number
  vocab_richness_score: number
}

export interface EvaluationReport {
  format_issues: FormatIssue[]
  plagiarism_matches: PlagiarismMatch[]
  ai_highlights: AiHighlight[]
  clarity_notes: string
  word_count: number
  ai_scan: AiScanDetail
}

export interface ResearchDocument {
  id: string
  research_problem_id: string
  student_user_id: string
  version: number
  file_url: string | null
  file_name: string | null
  plagiarism_score: number | null
  ai_content_score: number | null
  format_score: number | null
  clarity_score: number | null
  evaluation_report: EvaluationReport | null
  ai_model: string | null
  eval_job_id: string | null
  status: DocumentStatus
  guide_comment: string | null
  guide_reviewed_at: string | null
  submitted_at: string
}

export interface DocumentListResponse {
  items: ResearchDocument[]
  total: number
  offset: number
  limit: number
}

export interface DocumentSubmit {
  research_problem_id: string
  file_url: string
  file_name?: string
}

export interface GuideDocumentReviewRequest {
  decision: 'APPROVE' | 'REQUEST_REVISION'
  guide_comment?: string
}

// ── Viva ─────────────────────────────────────────────────────────────────────

export interface VivaQuestion {
  id: string
  text: string
  source: 'base' | 'followup'
  based_on_qid: string | null
  order: number
}

export interface ResponseEval {
  question_id: string
  coherence: number
  accuracy: number
  depth: number
  comment: string
}

export interface AIEvaluation {
  per_question: ResponseEval[]
  overall_score: number
  ai_model: string
  prompt_hash: string
  summary: string
}

export interface VivaSession {
  id: string
  research_problem_id: string
  document_id: string
  student_user_id: string
  guide_user_id: string
  session_token: string
  ai_questions: VivaQuestion[]
  ai_responses: Array<{ question_id: string; response_text: string; recorded_at: string }>
  video_url: string | null
  transcript: string | null
  ai_evaluation: AIEvaluation | null
  overall_ai_score: number | null
  guide_evaluation: Record<string, unknown> | null
  overall_guide_score: number | null
  consent_recorded: boolean
  status: VivaStatus
  scheduled_at: string
  expires_at: string
  completed_at: string | null
  ratified_at: string | null
}

export interface VivaListResponse {
  items: VivaSession[]
  total: number
  offset: number
  limit: number
}

export interface VivaScheduleRequest {
  research_problem_id: string
  document_id: string
}

export interface VivaOfflineResponse {
  question_id: string
  response_text: string
}

export interface VivaConductRequest {
  responses: VivaOfflineResponse[]
}

export interface VivaRatifyRequest {
  overall_guide_score: number
  guide_evaluation?: Record<string, { score: number; note: string }>
  ratification_note?: string
}

export interface VivaRespondRequest {
  response_text: string
}

// ── Job ───────────────────────────────────────────────────────────────────────

export interface JobStatus {
  job_id: string
  status: string
  result: Record<string, unknown> | null
  error: string | null
  created_at: string | null
  completed_at: string | null
}
