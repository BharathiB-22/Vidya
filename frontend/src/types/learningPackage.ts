// ---------------------------------------------------------------------------
// Enums — exact values from backend models.py
// ---------------------------------------------------------------------------

export type PackageStatus =
  | 'PENDING'
  | 'CURATING'
  | 'READY'
  | 'OUTDATED'

export type MaterialSourceType =
  | 'YOUTUBE'
  | 'ARXIV'
  | 'NPTEL'
  | 'MIT_OCW'
  | 'FACULTY_NOTE'

// ---------------------------------------------------------------------------
// JSONB sub-model
// ---------------------------------------------------------------------------

export interface ItemMetadata {
  thumbnail_url?:    string | null
  duration_seconds?: number | null
  arxiv_id?:         string | null
  abstract_snippet?: string | null
  authors?:          string[]
  publish_date?:     string | null
}

// ---------------------------------------------------------------------------
// Response interfaces
// ---------------------------------------------------------------------------

export interface LearningPackage {
  id:                  string
  syllabus_id:         string
  unit_number:         number
  version:             number
  status:              PackageStatus
  top_n:               number
  item_count:          number
  qdrant_indexed:      boolean
  ai_model:            string | null
  created_by_user_id:  string
  curated_at:          string | null
  created_at:          string
  updated_at:          string | null
}

export interface PackageItem {
  id:                  string
  package_id:          string
  source_type:         MaterialSourceType
  title:               string
  url:                 string | null
  content_hash:        string | null
  metadata:            ItemMetadata
  relevance_score:     number | null
  faculty_recommended: boolean
  added_by_user_id:    string | null
  display_order:       number
  qdrant_indexed:      boolean
  created_at:          string
  updated_at:          string | null
}

export interface LearningPackageListResponse {
  total:     number
  page:      number
  page_size: number
  items:     LearningPackage[]
}

// ---------------------------------------------------------------------------
// Query param shapes
// ---------------------------------------------------------------------------

export interface LearningPackageListFilters {
  syllabus_id?: string
  status?:      PackageStatus
  page?:        number
  page_size?:   number
}

// ---------------------------------------------------------------------------
// Q&A types
// ---------------------------------------------------------------------------

export type QARole = 'USER' | 'ASSISTANT'

export interface RAGSourceCitation {
  item_id:         string
  title:           string
  url:             string | null
  snippet:         string
  relevance_score: number | null
}

export interface QAMessage {
  id:         string
  session_id: string
  role:       QARole
  content:    string
  sources:    RAGSourceCitation[]
  created_at: string
}

export interface QASession {
  id:              string
  package_id:      string
  student_user_id: string
  created_at:      string
  updated_at:      string | null
}

export interface QASessionWithMessages extends QASession {
  messages: QAMessage[]
}

export interface RAGAnswerResponse {
  session_id: string
  message_id: string
  answer:     string
  sources:    RAGSourceCitation[]
  model_used: string | null
}

// ---------------------------------------------------------------------------
// Faculty curation types
// ---------------------------------------------------------------------------

export interface CurationJobResponse {
  job_id:     string
  package_id: string
  status:     string
}

export interface IndexJobResponse {
  job_id: string
  status: string
}

export interface JobStatus {
  job_id:   string
  status:   'PENDING' | 'RUNNING' | 'SUCCESS' | 'FAILED'
  message?: string | null
  error?:   string | null
}

export interface FacultyAddItemPayload {
  source_type: MaterialSourceType
  title:       string
  url?:        string | null
}
