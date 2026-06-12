// M09.8 — Admin (institution-wide) Examination Analytics
import { Building2 } from 'lucide-react'
import { ExamAnalyticsView } from '@/components/analytics/ExamAnalyticsView'

export default function AdminExamAnalyticsPage() {
  return (
    <ExamAnalyticsView
      title="Institution Examination Analytics"
      subtitle="Institution-wide outcomes, faculty workload & evaluation metrics"
      icon={Building2}
      sections={['overview', 'passfail', 'grades', 'subjects', 'batches', 'faculty']}
    />
  )
}
