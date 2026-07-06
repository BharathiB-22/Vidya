import type { SubjectDetailOut } from '@/lib/api/sis'

export interface SubjectTabProps {
  subject: SubjectDetailOut
  onNavigateTab: (key: string) => void
}
