// M09.8 — Dean Examination Analytics
import { BarChart2 } from 'lucide-react'
import { ExamAnalyticsView } from '@/components/analytics/ExamAnalyticsView'

export default function DeanExamAnalyticsPage() {
  return (
    <ExamAnalyticsView
      title="Examination Analytics"
      subtitle="Department performance — KPIs, pass/fail, subjects & grades"
      icon={BarChart2}
      sections={['overview', 'passfail', 'grades', 'subjects', 'batches']}
    />
  )
}
