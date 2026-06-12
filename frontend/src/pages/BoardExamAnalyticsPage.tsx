// M09.8 — Examination Board Analytics
import { Scale } from 'lucide-react'
import { ExamAnalyticsView } from '@/components/analytics/ExamAnalyticsView'

export default function BoardExamAnalyticsPage() {
  return (
    <ExamAnalyticsView
      title="Examination Board Analytics"
      subtitle="Result quality indicators — moderation & revaluation insights"
      icon={Scale}
      sections={['overview', 'grades', 'moderation', 'revaluation', 'subjects']}
    />
  )
}
