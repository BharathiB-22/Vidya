import type { LabAssignment } from '@/types/labs'

export interface LabGroupBucket {
  label: string
  items: LabAssignment[]
}

export interface LabGroupingResult {
  /** Assignments sharing a non-null lab_group, sorted by program_number. */
  grouped: LabGroupBucket[]
  /** Assignments with no lab_group — render flat, unchanged from before this feature. */
  ungrouped: LabAssignment[]
}

/**
 * Groups lab assignments by `lab_group` (e.g. "Python Lab" containing
 * Program 1..10), ordered by `program_number` within each group.
 * Assignments with lab_group == null are returned separately so existing/
 * legacy assignments keep rendering exactly as they did before this feature.
 */
export function groupByLabGroup(assignments: LabAssignment[]): LabGroupingResult {
  const groups = new Map<string, LabAssignment[]>()
  const ungrouped: LabAssignment[] = []

  for (const a of assignments) {
    if (!a.lab_group) {
      ungrouped.push(a)
      continue
    }
    const bucket = groups.get(a.lab_group) ?? []
    bucket.push(a)
    groups.set(a.lab_group, bucket)
  }

  const grouped: LabGroupBucket[] = Array.from(groups.entries()).map(([label, items]) => ({
    label,
    items: [...items].sort((a, b) => (a.program_number ?? 0) - (b.program_number ?? 0)),
  }))

  return { grouped, ungrouped }
}

/** "Program {n}" label, falling back to the assignment's own title. */
export function labProgramLabel(assignment: LabAssignment): string {
  return assignment.program_number != null ? `Program ${assignment.program_number}` : assignment.title
}
