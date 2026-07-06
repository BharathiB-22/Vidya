import { WelcomeCard } from '@/components/student/dashboard/WelcomeCard'
import { AcademicSummary } from '@/components/student/dashboard/AcademicSummary'
import { RecentActivity } from '@/components/student/dashboard/RecentActivity'
import { UpcomingDeadlines } from '@/components/student/dashboard/UpcomingDeadlines'
import { NotificationsWidget } from '@/components/student/dashboard/NotificationsWidget'
import { useStudentDashboardContext } from '@/components/student/dashboard/useStudentDashboardContext'

/**
 * The student's homepage — deliberately kept to one screen (no long scroll).
 * Calendar/Research/Labs widgets and the large quick-action grid moved to
 * their own dedicated sidebar pages instead of living here too.
 */
export function StudentDashboard() {
  const { semesterId, sessionId } = useStudentDashboardContext()

  return (
    <div className="space-y-4">
      <WelcomeCard />

      <AcademicSummary semesterId={semesterId} sessionId={sessionId} />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <UpcomingDeadlines sessionId={sessionId} />
        <NotificationsWidget />
        <RecentActivity />
      </div>
    </div>
  )
}
