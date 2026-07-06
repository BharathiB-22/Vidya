import api from '@/lib/api'

const BASE = '/calendar'

export type CalendarItemType =
  | 'HOLIDAY'
  | 'EVENT'
  | 'ANNOUNCEMENT'
  | 'ASSIGNMENT_DUE'
  | 'LAB_DUE'
  | 'EXAM'
  | 'VIVA'

export interface CalendarItem {
  id: string
  title: string
  item_type: CalendarItemType
  date: string
  start_time: string | null
  end_time: string | null
  all_day: boolean
  source_module: 'calendar' | 'assignments' | 'labs' | 'exam' | 'research'
  link: string | null
}

export async function getMyCalendar(dateFrom: string, dateTo: string): Promise<CalendarItem[]> {
  const { data } = await api.get<CalendarItem[]>(`${BASE}/me`, {
    params: { date_from: dateFrom, date_to: dateTo },
  })
  return data
}
