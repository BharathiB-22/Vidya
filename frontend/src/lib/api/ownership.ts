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
  /** APPOINTED = explicit program grant/coordinator; TEACHING = implied by courses taught. */
  source:           'APPOINTED' | 'TEACHING'
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
  program_id:      string | null
  program_name:    string | null
  program_code:    string | null
  department_id:   string | null
  department_name: string | null
}

export interface FacultyAcademicResponsibilities {
  faculty_user_id:    string
  home_department:    DeptInfo | null
  responsibilities:   string[]
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
// Ownership matrix — Department -> Program -> Semester -> Section -> Course -> Faculty
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

/** `section_id === null` is the "General" bucket (assigned at the whole-semester level). */
export interface MatrixSection {
  section_id: string | null
  name:       string
  courses:    MatrixCourse[]
}

export interface MatrixSemester {
  semester_id: string
  number:      number
  label:       string | null
  sections:    MatrixSection[]
}

export interface MatrixProgram {
  program_id:  string
  name:        string
  code:        string
  department:  DeptInfo | null
  semesters:   MatrixSemester[]
}

export interface MatrixDepartment {
  department_id: string | null
  name:          string
  code:          string | null
  programs:      MatrixProgram[]
}

export interface OwnershipMatrix {
  departments: MatrixDepartment[]
}

// ---------------------------------------------------------------------------
// Dashboard summary
// ---------------------------------------------------------------------------

export interface DashboardFacultyWorkload {
  faculty_user_id: string
  faculty_name:    string
  course_count:    number
  program_count:   number
  credits:         number
  section_count:   number
  hours_per_week:  number
}

export interface DashboardDepartmentSummary {
  department_id:   string | null
  department_name: string
  program_count:   number
  course_count:    number
  faculty_count:   number
  vacant_courses:  number
}

export interface OwnershipDashboardSummary {
  total_programs:        number
  total_courses:         number
  total_faculty:         number
  total_students:        number
  vacant_courses:        number
  program_coverage_pct:  number
  teaching_coverage_pct: number
  pending_faculty_allocation: number
  pending_course_allocation:  number
  faculty_workload:      DashboardFacultyWorkload[]
  department_summary:    DashboardDepartmentSummary[]
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

  getDashboardSummary: () =>
    api.get<OwnershipDashboardSummary>('/academics/dean/dashboard-summary')
      .then(r => r.data),
}
