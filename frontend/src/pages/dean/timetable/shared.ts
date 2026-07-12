import type { TimetableStatus } from '@/types/timetable'

export const STATUS_COLORS: Record<string, string> = {
  DRAFT:           'bg-gray-100 text-gray-600',
  PENDING_REVIEW:  'bg-amber-50 text-amber-700 ring-1 ring-amber-200',
  APPROVED:        'bg-sky-50 text-sky-700 ring-1 ring-sky-200',
  REJECTED:        'bg-red-50 text-red-700 ring-1 ring-red-200',
  PUBLISHED:       'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200',
}

/** What identifies a programme in a list, and nothing more.
 *
 *  A Dean running two live admissions sees "Master of Computer Applications"
 *  twice, so the batch years are the only thing that tells them apart. Prefer the
 *  short code when the backend has one: "MCA (2026–2028)" reads at a glance where
 *  the full title does not. */
export function programLabel(t: {
  program_name?: string | null
  program_code?: string | null
  academic_year?: string | null
}): string | null {
  const name = t.program_code || t.program_name
  if (!name) return null
  return t.academic_year ? `${name} (${t.academic_year})` : name
}

/** Unambiguous timetable label: "MCA (2026–2028) · Semester 1 · Section A"
 *  instead of a bare "Section A". Falls back gracefully when the
 *  program/semester chain is incomplete. */
export function timetableLabel(t: {
  program_name?: string | null
  program_code?: string | null
  academic_year?: string | null
  semester_label?: string | null
  section_name?: string | null
}): string {
  return [programLabel(t), t.semester_label, t.section_name ? `Section ${t.section_name}` : null]
    .filter(Boolean)
    .join(' · ') || 'Section'
}

/** Slots may only be added, moved, edited or removed in these states. Mirrors
 *  `TimetableService._require_editable` on the backend. */
export function isEditableStatus(status: TimetableStatus): boolean {
  return status === 'DRAFT' || status === 'REJECTED'
}
