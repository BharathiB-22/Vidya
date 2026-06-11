// M09.5 Digital Exams — TypeScript types

export type DigitalSessionStatus = 'DRAFT' | 'ACTIVE' | 'CLOSED'
export type DigitalAttemptStatus = 'IN_PROGRESS' | 'SUBMITTED' | 'SCORED' | 'FULLY_EVALUATED'

export interface DigitalExamSession {
  id:                string
  exam_paper_id:     string
  created_by:        string
  title:             string
  status:            DigitalSessionStatus
  max_duration_mins: number
  window_start:      string | null
  window_end:        string | null
  instructions:      string | null
  activated_at:      string | null
  closed_at:         string | null
  created_at:        string
  attempt_count:     number
  scored_count:      number
}

export interface DigitalSessionCreate {
  exam_paper_id:     string
  title:             string
  max_duration_mins?: number
  window_start?:     string | null
  window_end?:       string | null
  instructions?:     string | null
}

export interface DigitalSessionListResponse {
  items:  DigitalExamSession[]
  total:  number
  offset: number
  limit:  number
}

export interface DigitalExamAttempt {
  id:              string
  session_id:      string
  student_user_id: string
  status:          DigitalAttemptStatus
  started_at:      string
  expires_at:      string | null
  submitted_at:    string | null
  auto_scored_at:  string | null
  auto_score:      number | null
  mcq_max_score:   number | null
  created_at:      string
}

export type QuestionType = 'MCQ' | 'SHORT_ANSWER' | 'LONG_ANSWER' | 'PROBLEM_SOLVING'

export interface MCQOption {
  label: string
  text:  string
}

export interface DigitalResponseOut {
  id:              string
  attempt_id:      string
  question_id:     string
  question_type:   string | null
  selected_option: string | null
  response_text:   string | null
  is_auto_scored:  boolean
  auto_score:      number | null
  is_correct:      boolean | null
  answered_at:     string | null
}

export interface DigitalQuestionOut {
  id:            string
  unit_number:   number
  question_type: QuestionType
  bloom_level:   string
  question_text: string
  options:       MCQOption[] | null
  marks:         number
  section_label: string | null
  choice_group:  number | null
  saved_response: DigitalResponseOut | null
}

export interface DigitalAttemptDetailResponse {
  attempt:   DigitalExamAttempt
  questions: DigitalQuestionOut[]
}

export interface DigitalResponseIn {
  selected_option?: string | null
  response_text?:   string | null
}

export interface DigitalScoreBucket {
  label:   string
  pct_lo:  number
  pct_hi:  number
  count:   number
}

export interface DigitalSessionAnalytics {
  session_id:         string
  title:              string
  status:             string
  attempt_count:      number
  scored_count:       number
  in_progress_count:  number
  avg_score_pct:      number | null
  min_score_pct:      number | null
  max_score_pct:      number | null
  median_score_pct:   number | null
  pass_count:         number
  fail_count:         number
  pass_rate_pct:      number | null
  pass_threshold_pct: number
  score_buckets:      DigitalScoreBucket[]
}

export interface DigitalResultResponse {
  attempt:               DigitalExamAttempt
  responses:             DigitalResponseOut[]
  total_questions:       number
  mcq_questions:         number
  subjective_questions:  number
  attempted_count:       number
  correct_mcq:           number
}

// Phase D — Faculty Subjective Review

export interface FacultyScoreIn {
  score:  number
  note?:  string | null
}

export interface SubjectiveResponseItem {
  response_id:        string
  question_id:        string
  question_text:      string
  max_marks:          number
  response_text:      string | null
  faculty_score:      number | null
  faculty_note:       string | null
  faculty_scored_by:  string | null
  faculty_scored_at:  string | null
}

export interface SubjectiveScoreOut {
  response_id:       string
  question_id:       string
  faculty_score:     number
  faculty_note:      string | null
  faculty_scored_by: string
  faculty_scored_at: string
}

export interface SubjectivePendingAttempt {
  attempt_id:       string
  session_id:       string
  status:           DigitalAttemptStatus
  submitted_at:     string | null
  auto_score:       number | null
  mcq_max_score:    number | null
  subjective_count: number
  scored_count:     number
}

export interface SubjectiveQueueResponse {
  session_id: string
  items:      SubjectivePendingAttempt[]
  total:      number
}

export interface SubjectiveReviewResponse {
  attempt_id:        string
  session_id:        string
  status:            DigitalAttemptStatus
  submitted_at:      string | null
  auto_score:        number | null
  mcq_max_score:     number | null
  responses:         SubjectiveResponseItem[]
  total_subjective:  number
  scored_count:      number
  all_scored:        boolean
}

export interface SubjectiveSubmitIn {
  confirm: boolean
}

export interface SubjectiveSubmitResult {
  attempt_id:           string
  status:               DigitalAttemptStatus
  total_subjective:     number
  scored_count:         number
  total_faculty_score:  number
  fully_evaluated_at:   string
}
