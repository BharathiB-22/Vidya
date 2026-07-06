import api from '@/lib/api'

export interface NotificationItem {
  id: string
  notification_type: string
  title: string
  body: string
  entity_type: string | null
  entity_id: string | null
  is_read: boolean
  created_at: string
  read_at: string | null
}

export interface NotificationListResponse {
  total: number
  unread_count: number
  page: number
  page_size: number
  items: NotificationItem[]
}

export async function listNotifications(params?: {
  is_read?: boolean
  page?: number
  page_size?: number
}): Promise<NotificationListResponse> {
  const { data } = await api.get('/notifications', { params })
  return data
}

export async function markNotificationRead(notificationId: string): Promise<void> {
  await api.patch(`/notifications/${notificationId}/read`)
}

export async function markAllRead(): Promise<void> {
  await api.post('/notifications/read-all')
}

// ---------------------------------------------------------------------------
// Presentation metadata — category + label per notification_type.
// Unknown types fall back to the "System" category so new backend types render
// gracefully without a frontend change.
// ---------------------------------------------------------------------------

export type NotificationCategory =
  | 'Academic' | 'Assignments' | 'Labs' | 'Research' | 'Attendance' | 'Exam'
  | 'Announcements' | 'System'

const NOTIFICATION_CATEGORY: Record<string, NotificationCategory> = {
  COURSE_ASSIGNED:             'Academic',
  COURSE_ASSIGNMENT_REVOKED:   'Academic',
  PROGRAM_ASSIGNED:            'Academic',
  PROGRAM_ASSIGNMENT_REVOKED:  'Academic',
  ENROLLMENT_CREATED:          'Academic',
  ENROLLMENT_MOVED:            'Academic',
  ENROLLMENT_UNENROLLED:       'Academic',
  SYLLABUS_SUBMITTED:          'Academic',
  SYLLABUS_APPROVED:           'Academic',
  SYLLABUS_REJECTED:           'Academic',
  SYLLABUS_REVISION_REQUESTED: 'Academic',
  SYLLABUS_VERSION_CREATED:    'Academic',
  COURSE_KIT_SUBMITTED:        'Academic',
  COURSE_KIT_APPROVED:         'Academic',
  COURSE_KIT_REJECTED:         'Academic',
  ATTENDANCE_SHORTAGE_WARNING: 'Attendance',
  INTERNAL_MARKS_PUBLISHED:    'Exam',
  ASSIGNMENT_PUBLISHED:        'Assignments',
  ASSIGNMENT_GRADED:           'Assignments',
  ASSIGNMENT_RETURNED:         'Assignments',
  LAB_PUBLISHED:               'Labs',
  LAB_GRADED:                  'Labs',
  VIVA_SCHEDULED:              'Research',
}

export function notificationCategory(type: string): NotificationCategory {
  return NOTIFICATION_CATEGORY[type] ?? 'System'
}

/** Best-effort deep-link target for a notification, or null if none applies. */
export function notificationHref(n: NotificationItem): string | null {
  switch (n.entity_type) {
    case 'Syllabus':
      return n.entity_id ? `/syllabuses/${n.entity_id}` : '/syllabuses'
    case 'FacultyProgramAssignment':
    case 'SubjectAssignment':
      return '/faculty/my-responsibilities'
    case 'InternalMarksComponent':
    case 'InternalMarks':
      return '/sis/marks/me'
    case 'Assignment':
      return n.entity_id ? `/student/assignments/${n.entity_id}` : null
    case 'LabAssignment':
      return n.entity_id ? `/student/labs/${n.entity_id}` : null
    case 'VivaSession':
      return n.entity_id ? `/student/viva/${n.entity_id}` : null
    default:
      return null
  }
}