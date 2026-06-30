import api from '@/lib/api'

// ---------------------------------------------------------------------------
// Shared info blocks
// ---------------------------------------------------------------------------

export interface DeptInfo {
  id:   string
  name: string
  code: string
}

// ---------------------------------------------------------------------------
// Faculty responsibilities
// ---------------------------------------------------------------------------

export interface FacultyResponsibilityProgram {
  id:               string
  name:             string
  code:             string
  degree_type:      string
  department:       DeptInfo | null
  is_primary:       boolean
  assigned_by_name: string | null
  assigned_at:      string
}

export interface FacultyCourseEntry {
  assignment_id:   string
  course_id:       string
  code:            string
  title:           string
  semester_number: number
  semester_label:  string | null
  section_name:    string | null
  role_in_course:  string
  is_active:       boolean
}

export interface FacultyAcademicResponsibilities {
  faculty_user_id:    string
  departments:        DeptInfo[]
  programs:           FacultyResponsibilityProgram[]
  course_assignments: FacultyCourseEntry[]
}

export interface FacultyAcademicSummary {
  course_count:     number
  program_count:    number
  department_count: number
}

// ---------------------------------------------------------------------------
// Dean programs & faculty assignments
// ---------------------------------------------------------------------------

export interface DeanProgram {
  id:                   string
  name:                 string
  code:                 string
  degree_type:          string
  department:           DeptInfo | null
  active_faculty_count: number
}

export interface FacultyProgramAssignmentOut {
  id:              string
  faculty_user_id: string
  program_id:      string
  department_id:   string | null
  semester_id:     string | null
  section_id:      string | null
  is_primary:      boolean
  is_active:       boolean
  assigned_by:     string
  assigned_at:     string
  revoked_by:      string | null
  revoked_at:      string | null
  program_name:    string | null
  department_name: string | null
  faculty_name:    string | null
  faculty_email:   string | null
}

export interface FacultyProgramAssignCreate {
  faculty_user_id: string
  program_id:      string
  is_primary:      boolean
  semester_id?:    string | null
  section_id?:     string | null
}

// ---------------------------------------------------------------------------
// Workload
// ---------------------------------------------------------------------------

export interface FacultyWorkloadItem {
  faculty_user_id: string
  course_count:    number
  program_count:   number
}

export interface FacultyWorkloadResponse {
  items: FacultyWorkloadItem[]
}

// ---------------------------------------------------------------------------
// Ownership matrix
// ---------------------------------------------------------------------------

export interface MatrixFaculty {
  user_id:        string
  full_name:      string
  role_in_course: string
}

export interface MatrixCourse {
  course_id:   string
  code:        string
  title:       string
  course_type: string | null
  faculty:     MatrixFaculty[]
}

export interface MatrixSemester {
  semester_id: string
  number:      number
  label:       string | null
  courses:     MatrixCourse[]
}

export interface MatrixProgram {
  program_id:  string
  name:        string
  code:        string
  department:  DeptInfo | null
  semesters:   MatrixSemester[]
}

export interface OwnershipMatrix {
  programs: MatrixProgram[]
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

export const ownershipApi = {
  getFacultyResponsibilities: () =>
    api.get<FacultyAcademicResponsibilities>('/academics/faculty/me/responsibilities')
      .then(r => r.data),

  getFacultySummary: () =>
    api.get<FacultyAcademicSummary>('/academics/faculty/me/summary')
      .then(r => r.data),

  getDeanPrograms: () =>
    api.get<DeanProgram[]>('/academics/dean/programs')
      .then(r => r.data),

  getDeanFacultyAssignments: () =>
    api.get<FacultyProgramAssignmentOut[]>('/academics/dean/faculty-assignments')
      .then(r => r.data),

  getFacultyWorkload: () =>
    api.get<FacultyWorkloadResponse>('/academics/dean/faculty-workload')
      .then(r => r.data),

  assignFacultyToProgram: (body: FacultyProgramAssignCreate) =>
    api.post<FacultyProgramAssignmentOut>('/academics/dean/assign-faculty', body)
      .then(r => r.data),

  removeFacultyFromProgram: (id: string) =>
    api.delete<FacultyProgramAssignmentOut>(`/academics/dean/remove-faculty/${id}`)
      .then(r => r.data),

  getOwnershipMatrix: (programIds?: string[]) => {
    const params = programIds?.length
      ? { program_ids: programIds.join(',') }
      : undefined
    return api.get<OwnershipMatrix>('/academics/ownership-matrix', { params })
      .then(r => r.data)
  },
}
