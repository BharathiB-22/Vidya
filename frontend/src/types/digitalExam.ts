// M09.5 Digital Exams — TypeScript types

export type DigitalSessionStatus = 'DRAFT' | 'ACTIVE' | 'CLOSED'
export type DigitalAttemptStatus = 'IN_PROGRESS' | 'SUBMITTED' | 'SCORED'

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

export interface DigitalResultResponse {
  attempt:               DigitalExamAttempt
  responses:             DigitalResponseOut[]
  total_questions:       number
  mcq_questions:         number
  subjective_questions:  number
  attempted_count:       number
  correct_mcq:           number
}
