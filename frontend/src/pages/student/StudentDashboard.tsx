import { WelcomeCard } from '@/components/student/dashboard/WelcomeCard'
import { AcademicSummary } from '@/components/student/dashboard/AcademicSummary'
import { QuickActions } from '@/components/student/dashboard/QuickActions'
import { TodaySchedule } from '@/components/student/dashboard/TodaySchedule'
import { RecentActivity } from '@/components/student/dashboard/RecentActivity'
import { UpcomingDeadlines } from '@/components/student/dashboard/UpcomingDeadlines'
import { NotificationsWidget } from '@/components/student/dashboard/NotificationsWidget'
import { ResearchWidget } from '@/components/student/dashboard/ResearchWidget'
import { LabsWidget } from '@/components/student/dashboard/LabsWidget'
import { AcademicProgress } from '@/components/student/dashboard/AcademicProgress'
import { useStudentDashboardContext } from '@/components/student/dashboard/useStudentDashboardContext'

/**
 * The student's homepage — composed entirely from existing M06/M07/M11 "me"
 * and "student" endpoints. No new backend endpoints were introduced; see the
 * Phase 1 summary for what was deliberately left as an empty state (recent
 * activity tracking, class timetable) because no data source exists yet.
 */
export function StudentDashboard() {
  const { semesterId, sessionId } = useStudentDashboardContext()

  return (
    <div className="space-y-8">
      <WelcomeCard />

      <AcademicSummary semesterId={semesterId} sessionId={sessionId} />

      <QuickActions />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <TodaySchedule sessionId={sessionId} />
        <UpcomingDeadlines sessionId={sessionId} />
        <NotificationsWidget />
        <ResearchWidget />
        <LabsWidget />
        <AcademicProgress />
        <RecentActivity />
      </div>
    </div>
  )
}
