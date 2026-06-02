import api from '@/lib/api'

// ---------------------------------------------------------------------------
// Bulk generation
// ---------------------------------------------------------------------------

export interface GenerateStudentsPayload {
  usn_prefix: string
  program_code: string
  batch_year: number
  section?: string
  section_id?: string
  count: number
  start_seq?: number
  seq_width?: number
  email_domain: string
  default_password?: string
}

export interface GenerateStudentsResult {
  created: number
  skipped: number
  duplicate_usns: string[]
  duplicate_emails: string[]
  default_password: string
  enrollments_created: number
}

// ---------------------------------------------------------------------------
// File import (CSV and XLSX)
// ---------------------------------------------------------------------------

export interface CSVRowResult {
  row_number: number
  full_name: string
  email: string
  identifier: string | null
  is_valid: boolean
  errors: string[]
  section_resolved: boolean
  program_resolved: boolean
}

export interface CSVPreviewResponse {
  total_rows: number
  valid_rows: number
  invalid_rows: number
  duplicate_in_file: number
  duplicate_in_db: number
  rows: CSVRowResult[]
}

export interface CSVCommitResult {
  total: number
  created: number
  skipped: number
  errors: string[]
  enrollments_created: number
}

// ---------------------------------------------------------------------------
// Import context (optional — UI cascade selection)
// ---------------------------------------------------------------------------

export interface ImportContext {
  program_id?: string
  section_id?: string
}

// ---------------------------------------------------------------------------
// API client
// ---------------------------------------------------------------------------

export const onboardingApi = {
  // Bulk generation
  generateStudents: (payload: GenerateStudentsPayload): Promise<GenerateStudentsResult> =>
    api.post('/admin/onboarding/generate-students', payload).then((r) => r.data),

  // Students file import
  previewStudentsCSV: (file: File, ctx?: ImportContext): Promise<CSVPreviewResponse> => {
    const form = new FormData()
    form.append('file', file)
    if (ctx?.program_id) form.append('program_id', ctx.program_id)
    if (ctx?.section_id) form.append('section_id', ctx.section_id)
    return api.post('/admin/onboarding/import/students/preview', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then((r) => r.data)
  },

  commitStudentsCSV: (file: File, defaultPassword: string, ctx?: ImportContext): Promise<CSVCommitResult> => {
    const form = new FormData()
    form.append('file', file)
    form.append('default_password', defaultPassword)
    if (ctx?.program_id) form.append('program_id', ctx.program_id)
    if (ctx?.section_id) form.append('section_id', ctx.section_id)
    return api.post('/admin/onboarding/import/students/commit', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then((r) => r.data)
  },

  // Faculty file import
  previewFacultyCSV: (file: File): Promise<CSVPreviewResponse> => {
    const form = new FormData()
    form.append('file', file)
    return api.post('/admin/onboarding/import/faculty/preview', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then((r) => r.data)
  },

  commitFacultyCSV: (file: File, defaultPassword: string): Promise<CSVCommitResult> => {
    const form = new FormData()
    form.append('file', file)
    form.append('default_password', defaultPassword)
    return api.post('/admin/onboarding/import/faculty/commit', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then((r) => r.data)
  },

  // Template downloads — CSV
  downloadSampleStudentsCSV: () =>
    api.get('/admin/onboarding/sample-csv/students', { responseType: 'blob' }).then((r) => {
      _triggerDownload(r.data, 'students_template.csv', 'text/csv')
    }),

  downloadSampleFacultyCSV: () =>
    api.get('/admin/onboarding/sample-csv/faculty', { responseType: 'blob' }).then((r) => {
      _triggerDownload(r.data, 'faculty_template.csv', 'text/csv')
    }),

  // Template downloads — XLSX
  downloadSampleStudentsXLSX: () =>
    api.get('/admin/onboarding/sample-xlsx/students', { responseType: 'blob' }).then((r) => {
      _triggerDownload(r.data, 'students_template.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    }),

  downloadSampleFacultyXLSX: () =>
    api.get('/admin/onboarding/sample-xlsx/faculty', { responseType: 'blob' }).then((r) => {
      _triggerDownload(r.data, 'faculty_template.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    }),
}

function _triggerDownload(data: Blob, filename: string, mime: string) {
  const url = URL.createObjectURL(new Blob([data], { type: mime }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
