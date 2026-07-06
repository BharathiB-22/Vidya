import api from '@/lib/api'
import type {
  AddSlotPayload,
  CreatePeriodPayload,
  CreateTemplatePayload,
  CreateTimetablePayload,
  FacultyTimetable,
  StudentTimetable,
  Timetable,
  TimetableListItem,
  TimetableStatus,
  TimetableTemplate,
  UpdatePeriodPayload,
  UpdateTemplatePayload,
} from '@/types/timetable'

const BASE = '/timetable'

// ---------------------------------------------------------------------------
// Admin
// ---------------------------------------------------------------------------

export async function createTimetable(payload: CreateTimetablePayload): Promise<Timetable> {
  const { data } = await api.post<Timetable>(BASE, payload)
  return data
}

export async function listTimetables(filters?: {
  section_id?: string
  semester_id?: string
  status?: TimetableStatus
}): Promise<TimetableListItem[]> {
  const { data } = await api.get<TimetableListItem[]>(BASE, { params: filters })
  return data
}

export async function getTimetable(id: string): Promise<Timetable> {
  const { data } = await api.get<Timetable>(`${BASE}/${id}`)
  return data
}

export async function addSlot(id: string, payload: AddSlotPayload): Promise<Timetable> {
  const { data } = await api.post<Timetable>(`${BASE}/${id}/slots`, payload)
  return data
}

export async function deleteSlot(id: string, slotId: string): Promise<void> {
  await api.delete(`${BASE}/${id}/slots/${slotId}`)
}

export async function submitTimetable(id: string): Promise<Timetable> {
  const { data } = await api.post<Timetable>(`${BASE}/${id}/submit`)
  return data
}

export async function publishTimetable(id: string): Promise<Timetable> {
  const { data } = await api.post<Timetable>(`${BASE}/${id}/publish`)
  return data
}

// ---------------------------------------------------------------------------
// Dean
// ---------------------------------------------------------------------------

export async function listPendingTimetables(): Promise<TimetableListItem[]> {
  const { data } = await api.get<TimetableListItem[]>(`${BASE}/dean/pending`)
  return data
}

export async function approveTimetable(id: string): Promise<Timetable> {
  const { data } = await api.post<Timetable>(`${BASE}/${id}/approve`)
  return data
}

export async function rejectTimetable(id: string, comment: string): Promise<Timetable> {
  const { data } = await api.post<Timetable>(`${BASE}/${id}/reject`, { comment })
  return data
}

// ---------------------------------------------------------------------------
// Student / Faculty
// ---------------------------------------------------------------------------

export async function getMyStudentTimetable(): Promise<StudentTimetable | null> {
  const { data } = await api.get<StudentTimetable | null>(`${BASE}/me`)
  return data
}

export async function getMyFacultyTimetable(): Promise<FacultyTimetable> {
  const { data } = await api.get<FacultyTimetable>(`${BASE}/mine`)
  return data
}

// ---------------------------------------------------------------------------
// Templates (Dean) — academic schedule configuration: working days, periods, breaks
// ---------------------------------------------------------------------------

export async function createTemplate(payload: CreateTemplatePayload): Promise<TimetableTemplate> {
  const { data } = await api.post<TimetableTemplate>(`${BASE}/templates`, payload)
  return data
}

export async function listTemplates(departmentId?: string): Promise<TimetableTemplate[]> {
  const { data } = await api.get<TimetableTemplate[]>(`${BASE}/templates`, {
    params: departmentId ? { department_id: departmentId } : undefined,
  })
  return data
}

export async function getTemplate(id: string): Promise<TimetableTemplate> {
  const { data } = await api.get<TimetableTemplate>(`${BASE}/templates/${id}`)
  return data
}

export async function updateTemplate(id: string, payload: UpdateTemplatePayload): Promise<TimetableTemplate> {
  const { data } = await api.patch<TimetableTemplate>(`${BASE}/templates/${id}`, payload)
  return data
}

export async function addPeriod(templateId: string, payload: CreatePeriodPayload): Promise<TimetableTemplate> {
  const { data } = await api.post<TimetableTemplate>(`${BASE}/templates/${templateId}/periods`, payload)
  return data
}

export async function updatePeriod(
  templateId: string,
  periodId: string,
  payload: UpdatePeriodPayload
): Promise<TimetableTemplate> {
  const { data } = await api.patch<TimetableTemplate>(`${BASE}/templates/${templateId}/periods/${periodId}`, payload)
  return data
}

export async function deletePeriod(templateId: string, periodId: string): Promise<void> {
  await api.delete(`${BASE}/templates/${templateId}/periods/${periodId}`)
}
