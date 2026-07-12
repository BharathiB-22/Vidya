import api from '@/lib/api'
import type {
  AddSlotPayload,
  CreatePeriodPayload,
  CreateTemplatePayload,
  CreateTimetablePayload,
  FacultyTimetable,
  StudentTimetable,
  SwapSlotsPayload,
  Timetable,
  TimetableListItem,
  TimetableSlot,
  TimetableStatus,
  TimetableTemplate,
  TimetableTemplateListItem,
  UpdatePeriodPayload,
  UpdateSlotPayload,
  UpdateTemplatePayload,
  UpdateTimetablePayload,
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

/** Re-point a draft timetable at a different schedule template. Refused if an
 *  existing entry sits on a period the new template does not teach. */
export async function updateTimetable(id: string, payload: UpdateTimetablePayload): Promise<Timetable> {
  const { data } = await api.patch<Timetable>(`${BASE}/${id}`, payload)
  return data
}

export async function addSlot(id: string, payload: AddSlotPayload): Promise<Timetable> {
  const { data } = await api.post<Timetable>(`${BASE}/${id}/slots`, payload)
  return data
}

/** Move a slot to another day/period, or change its faculty, room or remarks.
 *  The server validates the resulting position, so a rejected move leaves the
 *  entry exactly where it was. */
export async function updateSlot(
  id: string, slotId: string, payload: UpdateSlotPayload,
): Promise<TimetableSlot> {
  const { data } = await api.patch<TimetableSlot>(`${BASE}/${id}/slots/${slotId}`, payload)
  return data
}

/** Exchange the day/period of two slots. Returns both in their new positions. */
export async function swapSlots(id: string, payload: SwapSlotsPayload): Promise<TimetableSlot[]> {
  const { data } = await api.post<TimetableSlot[]>(`${BASE}/${id}/slots/swap`, payload)
  return data
}

export async function deleteSlot(id: string, slotId: string): Promise<void> {
  await api.delete(`${BASE}/${id}/slots/${slotId}`)
}

/** Deletes the timetable and its slots. Refused once PUBLISHED — students and
 *  faculty are reading it. Removes no programme, course, faculty or assignment. */
export async function deleteTimetable(id: string): Promise<void> {
  await api.delete(`${BASE}/${id}`)
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

export async function listTemplates(departmentId?: string): Promise<TimetableTemplateListItem[]> {
  const { data } = await api.get<TimetableTemplateListItem[]>(`${BASE}/templates`, {
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

export async function deleteTemplate(id: string): Promise<void> {
  await api.delete(`${BASE}/templates/${id}`)
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
