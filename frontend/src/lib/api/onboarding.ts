import api from '@/lib/api'

// ---------------------------------------------------------------------------
// Academic master data
// ---------------------------------------------------------------------------

export interface Department {
  id: string
  name: string
  code: string
  is_active: boolean
}

export interface Program {
  id: string
  name: string
  code: string
  dept_id: string | null
  duration_years: number
  is_active: boolean
}

export interface DepartmentCreatePayload {
  name: string
  code: string
}

export interface ProgramCreatePayload {
  name: string
  code: string
  dept_id?: string
  duration_years?: number
}

// ---------------------------------------------------------------------------
// Bulk generation
// ---------------------------------------------------------------------------

export interface GenerateStudentsPayload {
  usn_prefix: string
  program_code: string
  batch_year: number
  section?: string
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
}

// ---------------------------------------------------------------------------
// CSV import
// ---------------------------------------------------------------------------

export interface CSVRowResult {
  row_number: number
  full_name: string
  email: string
  identifier: string | null
  is_valid: boolean
  errors: string[]
}

export interface CSVPreviewResponse {
  total_rows: number
  valid_rows: number
  invalid_rows: number
  rows: CSVRowResult[]
}

export interface CSVCommitResult {
  total: number
  created: number
  skipped: number
  errors: string[]
}

// ---------------------------------------------------------------------------
// API client
// ---------------------------------------------------------------------------

export const onboardingApi = {
  // Departments
  listDepartments: (): Promise<Department[]> =>
    api.get('/admin/onboarding/departments').then((r) => r.data),

  createDepartment: (payload: DepartmentCreatePayload): Promise<Department> =>
    api.post('/admin/onboarding/departments', payload).then((r) => r.data),

  // Programs
  listPrograms: (): Promise<Program[]> =>
    api.get('/admin/onboarding/programs').then((r) => r.data),

  createProgram: (payload: ProgramCreatePayload): Promise<Program> =>
    api.post('/admin/onboarding/programs', payload).then((r) => r.data),

  // Bulk generation
  generateStudents: (payload: GenerateStudentsPayload): Promise<GenerateStudentsResult> =>
    api.post('/admin/onboarding/generate-students', payload).then((r) => r.data),

  // Students CSV
  previewStudentsCSV: (file: File): Promise<CSVPreviewResponse> => {
    const form = new FormData()
    form.append('file', file)
    return api.post('/admin/onboarding/import/students/preview', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then((r) => r.data)
  },

  commitStudentsCSV: (file: File, defaultPassword: string): Promise<CSVCommitResult> => {
    const form = new FormData()
    form.append('file', file)
    form.append('default_password', defaultPassword)
    return api.post('/admin/onboarding/import/students/commit', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then((r) => r.data)
  },

  // Faculty CSV
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

  // Sample CSV downloads (returns blob URL)
  downloadSampleStudentsCSV: () =>
    api.get('/admin/onboarding/sample-csv/students', { responseType: 'blob' }).then((r) => {
      const url = URL.createObjectURL(new Blob([r.data], { type: 'text/csv' }))
      const a = document.createElement('a')
      a.href = url
      a.download = 'students_sample.csv'
      a.click()
      URL.revokeObjectURL(url)
    }),

  downloadSampleFacultyCSV: () =>
    api.get('/admin/onboarding/sample-csv/faculty', { responseType: 'blob' }).then((r) => {
      const url = URL.createObjectURL(new Blob([r.data], { type: 'text/csv' }))
      const a = document.createElement('a')
      a.href = url
      a.download = 'faculty_sample.csv'
      a.click()
      URL.revokeObjectURL(url)
    }),
}
