import api from '@/lib/api'

export interface Department {
  id: string
  school_id: string | null
  name: string
  code: string
  description: string | null
  is_active: boolean
  created_at: string
  updated_at: string | null
}

export interface AcadProgram {
  id: string
  department_id: string
  name: string
  code: string
  degree_type: string
  duration_years: number
  is_active: boolean
  created_at: string
  updated_at: string | null
}

export interface Batch {
  id: string
  program_id: string
  name: string
  start_year: number
  end_year: number
  is_active: boolean
  created_at: string
  updated_at: string | null
}

export interface Semester {
  id: string
  batch_id: string
  number: number
  label: string | null
  start_date: string | null
  end_date: string | null
  is_active: boolean
  created_at: string
  // Populated by the list endpoint only (resolved server-side via batch -> program).
  program_id:   string | null
  program_name: string | null
  program_code: string | null
}

export interface Section {
  id: string
  semester_id: string
  name: string
  max_strength: number | null
  is_active: boolean
  created_at: string
}

export interface GenerateSemestersResult {
  created: number
  skipped: number
  semesters: Semester[]
}

const B = '/academics'

export const academicsApi = {
  // Departments
  listDepartments: (includeInactive = false) =>
    api.get<Department[]>(`${B}/departments`, { params: { include_inactive: includeInactive } }).then(r => r.data),
  createDepartment: (body: { name: string; code: string; description?: string; school_id?: string }) =>
    api.post<Department>(`${B}/departments`, body).then(r => r.data),
  updateDepartment: (id: string, body: Partial<{ name: string; code: string; description: string; is_active: boolean; school_id: string }>) =>
    api.put<Department>(`${B}/departments/${id}`, body).then(r => r.data),

  // Programs
  listPrograms: (departmentId?: string, includeInactive = false) =>
    api.get<AcadProgram[]>(`${B}/programs`, { params: { department_id: departmentId || undefined, include_inactive: includeInactive } }).then(r => r.data),
  getProgram: (id: string) =>
    api.get<AcadProgram>(`${B}/programs/${id}`).then(r => r.data),
  createProgram: (body: { department_id: string; name: string; code: string; degree_type: string; duration_years: number }) =>
    api.post<AcadProgram>(`${B}/programs`, body).then(r => r.data),
  updateProgram: (id: string, body: Partial<{ name: string; code: string; degree_type: string; duration_years: number; is_active: boolean }>) =>
    api.put<AcadProgram>(`${B}/programs/${id}`, body).then(r => r.data),

  // Dean governance — WHICH programmes a Dean governs.
  //
  // Reads of this scope have existed since Phase B (the Dean's curriculum, faculty,
  // students and timetable all rest on it). The WRITE did not: the only rows any tenant
  // had were put there by a one-off backfill migration, so a Dean created afterwards
  // governed nothing and the Users page's "Programs" column could never be filled in.
  // ADMIN only — a Dean must not be able to widen his own scope.
  listDeanPrograms: (deanUserId: string) =>
    api.get<string[]>(`${B}/deans/${deanUserId}/programs`).then(r => r.data),
  setDeanPrograms: (deanUserId: string, programIds: string[]) =>
    api.put<string[]>(`${B}/deans/${deanUserId}/programs`, { program_ids: programIds }).then(r => r.data),

  // Batches
  listBatches: (programId?: string, includeInactive = false) =>
    api.get<Batch[]>(`${B}/batches`, { params: { program_id: programId || undefined, include_inactive: includeInactive } }).then(r => r.data),
  createBatch: (body: { program_id: string; name: string; start_year: number; end_year: number }) =>
    api.post<Batch>(`${B}/batches`, body).then(r => r.data),
  updateBatch: (id: string, body: Partial<{ name: string; is_active: boolean }>) =>
    api.put<Batch>(`${B}/batches/${id}`, body).then(r => r.data),
  generateSemesters: (batchId: string) =>
    api.post<GenerateSemestersResult>(`${B}/batches/${batchId}/generate-semesters`).then(r => r.data),

  // Semesters
  listSemesters: (batchId?: string, includeInactive = false) =>
    api.get<Semester[]>(`${B}/semesters`, { params: { batch_id: batchId || undefined, include_inactive: includeInactive } }).then(r => r.data),
  createSemester: (body: { batch_id: string; number: number; label?: string }) =>
    api.post<Semester>(`${B}/semesters`, body).then(r => r.data),
  updateSemester: (id: string, body: Partial<{ label: string | null; is_active: boolean }>) =>
    api.put<Semester>(`${B}/semesters/${id}`, body).then(r => r.data),

  // Sections
  listSections: (semesterId?: string, includeInactive = false) =>
    api.get<Section[]>(`${B}/sections`, { params: { semester_id: semesterId || undefined, include_inactive: includeInactive } }).then(r => r.data),
  createSection: (body: { semester_id: string; name: string; max_strength?: number }) =>
    api.post<Section>(`${B}/sections`, body).then(r => r.data),
  updateSection: (id: string, body: Partial<{ name: string; max_strength: number | null; is_active: boolean }>) =>
    api.put<Section>(`${B}/sections/${id}`, body).then(r => r.data),
}
