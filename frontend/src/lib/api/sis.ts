import api from '@/lib/api'

// ---------------------------------------------------------------------------
// Schools
// ---------------------------------------------------------------------------

export interface School {
  id: string
  code: string
  name: string
  description: string | null
  is_active: boolean
  created_at: string
  updated_at: string | null
}

// ---------------------------------------------------------------------------
// Enrollment types (M11-002)
// ---------------------------------------------------------------------------

export interface RosterStudent {
  enrollment_id: string
  student_id: string
  full_name: string
  email: string
  identifier: string | null
  enrolled_at: string
  is_active: boolean
}

export interface EnrollmentOut {
  id: string
  student_id: string
  section_id: string
  enrolled_at: string
  is_active: boolean
}

export interface StudentSummary {
  id: string
  full_name: string
  email: string
  identifier: string | null
  is_enrolled: boolean
}

export interface ProgramSummary {
  id: string
  name: string
  code: string
  degree_type: string
}

export interface DeptSummary {
  id: string
  name: string
  code: string
}

export interface BatchSummary {
  id: string
  name: string
  start_year: number
  end_year: number
}

export interface SemesterSummary {
  id: string
  number: number
  label: string | null
}

export interface SectionSummary {
  id: string
  name: string
}

export interface EnrollmentSummary {
  enrollment_id: string
  section: SectionSummary
  semester: SemesterSummary
}

export interface StudentProfile {
  student_id: string
  full_name: string
  email: string
  identifier: string | null
  program: ProgramSummary | null
  department: DeptSummary | null
  batch: BatchSummary | null
  enrollment: EnrollmentSummary | null
}

export interface DashboardCounts {
  schools: number
  departments: number
  programs: number
  active_batches: number
  semesters: number
  sections: number
  enrolled_students: number
  total_students: number
  total_faculty: number
}

// ---------------------------------------------------------------------------
// Directory types (H50)
// ---------------------------------------------------------------------------

export interface DirectoryPage<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface StudentDirectoryItem {
  user_id: string
  full_name: string
  email: string
  identifier: string | null
  usn: string | null
  admission_year: number | null
  program: { id: string; name: string; code: string; degree_type: string } | null
  department: { id: string; name: string; code: string } | null
  batch: { id: string; name: string; start_year: number; end_year: number } | null
  current_section: { id: string; name: string } | null
  is_active: boolean
}

export interface StudentDetailOut extends StudentDirectoryItem {
  date_of_birth: string | null
  phone: string | null
  address_line1: string | null
  address_city: string | null
  address_state: string | null
  emergency_contact_name: string | null
  emergency_contact_phone: string | null
  photo_url: string | null
  notes: string | null
  profile_created_at: string | null
  profile_updated_at: string | null
}

export interface FacultyDirectoryItem {
  user_id: string
  full_name: string
  email: string
  employee_id: string | null
  designation: string | null
  specialization: string | null
  primary_department: { id: string; name: string; code: string } | null
  photo_url: string | null
  is_active: boolean
}

export interface FacultyDetailOut extends FacultyDirectoryItem {
  identifier: string | null
  qualifications: string | null
  bio: string | null
  office_location: string | null
  phone: string | null
  joining_date: string | null
  active_assignments: {
    course: { id: string; name: string; code: string }
    semester_label: string
    role: string
  }[]
  profile_created_at: string | null
  profile_updated_at: string | null
}

export interface StudentProfileUpsert {
  usn?: string
  admission_year?: number
  date_of_birth?: string
  phone?: string
  address_line1?: string
  address_city?: string
  address_state?: string
  emergency_contact_name?: string
  emergency_contact_phone?: string
  photo_url?: string
  notes?: string
}

export interface FacultyProfileUpsert {
  employee_id: string
  designation?: string
  qualifications?: string
  bio?: string
  office_location?: string
  phone?: string
  joining_date?: string
  specialization?: string
  primary_department_id?: string
  photo_url?: string
}

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------

export const sisApi = {
  // Schools
  listSchools: (includeInactive = false) =>
    api.get<School[]>('/sis/schools', { params: { include_inactive: includeInactive } }).then(r => r.data),

  getSchool: (id: string) =>
    api.get<School>(`/sis/schools/${id}`).then(r => r.data),

  createSchool: (body: { code: string; name: string; description?: string }) =>
    api.post<School>('/sis/schools', body).then(r => r.data),

  updateSchool: (id: string, body: Partial<{ code: string; name: string; description: string; is_active: boolean }>) =>
    api.put<School>(`/sis/schools/${id}`, body).then(r => r.data),

  deleteSchool: (id: string) =>
    api.delete(`/sis/schools/${id}`).then(r => r.data),

  // Dashboard counts
  getDashboardCounts: () =>
    api.get<DashboardCounts>('/sis/dashboard/counts').then(r => r.data),

  // Section roster
  getRoster: (sectionId: string, includeInactive = false) =>
    api.get<RosterStudent[]>(`/sis/sections/${sectionId}/roster`, {
      params: { include_inactive: includeInactive },
    }).then(r => r.data),

  // Student list (enroll picker)
  listStudents: (search?: string) =>
    api.get<StudentSummary[]>('/sis/students', { params: search ? { search } : {} }).then(r => r.data),

  // Student academic profile
  getStudentProfile: (studentId: string) =>
    api.get<StudentProfile>(`/sis/students/${studentId}/profile`).then(r => r.data),

  // Enrollment mutations
  enrollStudent: (studentId: string, sectionId: string) =>
    api.post<EnrollmentOut>('/sis/enrollments', { student_id: studentId, section_id: sectionId }).then(r => r.data),

  unenrollStudent: (enrollmentId: string) =>
    api.delete(`/sis/enrollments/${enrollmentId}`).then(r => r.data),

  moveStudent: (enrollmentId: string, targetSectionId: string) =>
    api.post<EnrollmentOut>(`/sis/enrollments/${enrollmentId}/move`, { target_section_id: targetSectionId }).then(r => r.data),

  // ---------------------------------------------------------------------------
  // Directory (H50)
  // ---------------------------------------------------------------------------

  listStudentDirectory: (params: {
    page?: number; page_size?: number; search?: string
    program_id?: string; batch_id?: string; section_id?: string; is_active?: boolean
  } = {}) =>
    api.get<DirectoryPage<StudentDirectoryItem>>('/sis/directory/students', { params }).then(r => r.data),

  getStudentDetail: (userId: string) =>
    api.get<StudentDetailOut>(`/sis/directory/students/${userId}`).then(r => r.data),

  upsertStudentProfile: (userId: string, body: StudentProfileUpsert) =>
    api.put<StudentDetailOut>(`/sis/directory/students/${userId}/profile`, body).then(r => r.data),

  listFacultyDirectory: (params: {
    page?: number; page_size?: number; search?: string
    department_id?: string; is_active?: boolean
  } = {}) =>
    api.get<DirectoryPage<FacultyDirectoryItem>>('/sis/directory/faculty', { params }).then(r => r.data),

  getFacultyDetail: (userId: string) =>
    api.get<FacultyDetailOut>(`/sis/directory/faculty/${userId}`).then(r => r.data),

  upsertFacultyProfile: (userId: string, body: FacultyProfileUpsert) =>
    api.put<FacultyDetailOut>(`/sis/directory/faculty/${userId}/profile`, body).then(r => r.data),

  listDepartmentFaculty: (deptId: string) =>
    api.get<DirectoryPage<FacultyDirectoryItem>>(`/sis/departments/${deptId}/faculty`).then(r => r.data),
}
