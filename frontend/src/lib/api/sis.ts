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
}
