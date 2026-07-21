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
  VIVA_RATIFIED:               'Research',
  RESEARCH_PROPOSAL_SUBMITTED: 'Research',
  RESEARCH_PROPOSAL_EVALUATED: 'Research',
  RESEARCH_PROPOSAL_DECIDED:   'Research',
  RESEARCH_DOCUMENT_EVALUATED: 'Research',
  RESEARCH_DOCUMENT_REVIEWED:  'Research',
  RESEARCH_EVALUATION_FAILED:  'Research',
}

export function notificationCategory(type: string): NotificationCategory {
  return NOTIFICATION_CATEGORY[type] ?? 'System'
}

/** Best-effort deep-link target for a notification, or null if none applies.
 *
 *  `viewerRole` is the recipient's role — they are reading their own
 *  notifications, so the viewer IS the recipient. It disambiguates the entity
 *  types that staff and students share: entity_type 'Assignment' means "the
 *  coursework I set" to a faculty member and "the coursework I was given" to a
 *  student, and those are different pages. Optional, and when it is absent the
 *  destinations are exactly what they were before it existed.
 */
export function notificationHref(
  n: NotificationItem,
  viewerRole?: string | null,
): string | null {
  const isStudent = viewerRole === 'STUDENT'
  // Staff only when we positively know the role. An unknown role keeps the
  // long-standing student default rather than guessing a staff route.
  const isStaff = Boolean(viewerRole) && !isStudent

  // Coursework EVALUATION notifications must open the evaluator's review surface,
  // not the student page — even though they share entity_type 'Assignment' /
  // 'AssignmentSubmission' with student notifications. Discriminate by type, and
  // do it BEFORE the entity_type switch so nothing else changes.

  // Sent ONLY to the assignment's owning faculty when an evaluator saves a
  // recommendation, so it resolves by type alone and does not depend on the
  // caller having passed a role — this notification must never resolve to a
  // /student/* route for anyone.
  if (n.notification_type === 'ASSIGNMENT_EVALUATION_COMPLETED') {
    return n.entity_id
      ? `/faculty/assignments/${n.entity_id}/submissions`
      : '/faculty/assignments'
  }
  if (n.notification_type === 'ASSIGNMENT_EVALUATOR_ASSIGNED') {
    // entity_id is the assignment id — open its Evaluation Center (student queue),
    // never the student page or the generic My Evaluations list.
    return n.entity_id ? `/faculty/evaluation-center/${n.entity_id}` : '/faculty/evaluation-center'
  }
  if (n.notification_type === 'REVIEW_REQUESTED' && n.entity_type === 'AssignmentSubmission') {
    // This notification carries a submission id (not an assignment id), so send
    // the evaluator to the Evaluation Center list to open the assignment. Gating
    // on entity_type keeps non-coursework REVIEW_REQUESTED (exam scripts,
    // research) on their own routes below.
    return '/faculty/evaluation-center'
  }

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
      if (!n.entity_id) return null
      // Shared entity type. Staff get the review surface they can actually open;
      // students get their own assignment page, which itself refuses to show a
      // result until the faculty has released it.
      return isStaff
        ? `/faculty/assignments/${n.entity_id}/submissions`
        : `/student/assignments/${n.entity_id}`
    case 'LabAssignment':
      return n.entity_id ? `/student/labs/${n.entity_id}` : null
    // ── M07 Research Supervision ────────────────────────────────────────────
    // Guides and students share these entity types and have entirely separate
    // surfaces for them, so the recipient's role picks the route.
    case 'ResearchProblem':
      if (!n.entity_id) return isStaff ? '/research/problems' : '/student/research'
      return isStaff
        ? `/research/problems/${n.entity_id}`
        : `/student/research/${n.entity_id}`
    case 'ResearchDocument':
      // Guide-only: there is no student-facing document route, so notifications
      // sent to students about a document carry their PROBLEM id instead and
      // resolve through the ResearchProblem case above.
      return n.entity_id ? `/research/documents/${n.entity_id}` : '/research/problems'
    case 'VivaSession':
      // entity_id is the session TOKEN for student-facing viva notifications and
      // the viva id for guide-facing ones — the two routes are keyed differently.
      if (!n.entity_id) return isStaff ? '/research/problems' : '/student/research'
      return isStaff
        ? `/research/vivas/${n.entity_id}`
        : `/student/viva/${n.entity_id}`
    default:
      return null
  }
}