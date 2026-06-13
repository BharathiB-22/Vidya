// M09.7 OCR Review Queue — API client
import api from '@/lib/api'

const BASE = '/ocr-review'

// ---- Types (inline — no separate types file needed) -------------------------

export interface OcrDashboard {
  pending_total:       number
  in_review_total:     number
  ocr_failure_count:   number
  low_confidence_count: number
  quality_issue_count: number
  medium_confidence_count: number
  completed_today:     number
}

export interface OcrThreshold {
  id:                        string
  scope:                     'GLOBAL' | 'EXAM'
  scope_ref_id?:             string | null
  low_confidence_threshold:  number
  medium_confidence_threshold: number
  updated_at:                string
}

export interface OcrQueueItem {
  id:                  string
  script_id:           string
  masked_id?:          string | null
  exam_paper_id?:      string | null
  priority_category:   string
  priority_score:      number
  ocr_confidence?:     number | null
  review_status:       string
  assigned_reviewer_id?: string | null
  enqueued_at:         string
  review_started_at?:  string | null
  review_completed_at?: string | null
}

export interface OcrQueueListResponse {
  items:  OcrQueueItem[]
  total:  number
  page:   number
  pages:  number
}

export interface OcrReviewDetail extends OcrQueueItem {
  original_ocr_text?:  string | null
  corrected_text?:     string | null
  reviewer_notes?:     string | null
  action_taken?:       string | null
  page_image_keys?:    string[]
  scan_quality_flags?: Array<{ type: string; page: number; severity: string; description: string }>
}

export interface OcrActionResponse {
  queue_id:      string
  review_status: string
  action_taken?: string | null
  message:       string
}

// ---- API functions ----------------------------------------------------------

export async function getDashboard(): Promise<OcrDashboard> {
  const { data } = await api.get(`${BASE}/dashboard`)
  return data
}

export async function getEffectiveThreshold(examPaperId?: string): Promise<OcrThreshold> {
  const { data } = await api.get(`${BASE}/threshold`, {
    params: examPaperId ? { exam_paper_id: examPaperId } : undefined,
  })
  return data
}

export async function getAllThresholds(): Promise<OcrThreshold[]> {
  const { data } = await api.get(`${BASE}/threshold/all`)
  return data
}

export async function setThreshold(payload: {
  scope:                     'GLOBAL' | 'EXAM'
  scope_ref_id?:             string
  low_confidence_threshold:  number
  medium_confidence_threshold: number
}): Promise<OcrThreshold> {
  const { data } = await api.post(`${BASE}/threshold`, payload)
  return data
}

export interface QueueListParams {
  exam_paper_id?:    string
  priority_category?: string
  show_completed?:   boolean
  page?:             number
  page_size?:        number
}

export async function listQueue(params?: QueueListParams): Promise<OcrQueueListResponse> {
  const { data } = await api.get(BASE, { params })
  return data
}

export async function getDetail(queueId: string): Promise<OcrReviewDetail> {
  const { data } = await api.get(`${BASE}/${queueId}`)
  return data
}

export async function startReview(queueId: string): Promise<OcrActionResponse> {
  const { data } = await api.post(`${BASE}/${queueId}/start`)
  return data
}

export async function acceptOcr(queueId: string, notes?: string): Promise<OcrActionResponse> {
  const { data } = await api.post(`${BASE}/${queueId}/accept`, { reviewer_notes: notes ?? '' })
  return data
}

export async function correctOcr(queueId: string, correctedText: string, notes?: string): Promise<OcrActionResponse> {
  const { data } = await api.post(`${BASE}/${queueId}/correct`, {
    corrected_text: correctedText,
    reviewer_notes: notes ?? '',
  })
  return data
}

export async function rerunOcr(queueId: string, notes?: string): Promise<OcrActionResponse> {
  const { data } = await api.post(`${BASE}/${queueId}/rerun`, { reviewer_notes: notes ?? '' })
  return data
}

export async function escalateOcr(queueId: string, notes: string): Promise<OcrActionResponse> {
  const { data } = await api.post(`${BASE}/${queueId}/escalate`, { reviewer_notes: notes })
  return data
}

export async function markUnreadable(queueId: string, notes: string): Promise<OcrActionResponse> {
  const { data } = await api.post(`${BASE}/${queueId}/unreadable`, { reviewer_notes: notes })
  return data
}
