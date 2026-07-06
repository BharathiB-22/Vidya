import { useNavigate } from 'react-router-dom'
import {
  FlaskConical, Microscope, Monitor, CalendarCheck, BookMarked, Ticket,
  CalendarDays, Award, UserCircle2, Bell, BookOpen,
} from 'lucide-react'
import { ModuleCardItem, type ModuleCard } from '@/components/dashboard/shared'

const ACTIONS: ModuleCard[] = [
  { title: 'My Subjects', description: 'Course kits, learning materials, syllabus and more — organised by subject.', to: '/student/subjects', icon: BookOpen, roles: ['STUDENT'], badge: 'bg-teal-50 text-teal-600 border-teal-100', bar: 'bg-teal-500', section: '' },
  { title: 'My Labs', description: 'View assignments and submit your work.', to: '/student/labs', icon: FlaskConical, roles: ['STUDENT'], badge: 'bg-emerald-50 text-emerald-600 border-emerald-100', bar: 'bg-emerald-500', section: '' },
  { title: 'My Research', description: 'Track your proposal, documents, and viva.', to: '/student/research', icon: Microscope, roles: ['STUDENT'], badge: 'bg-purple-50 text-purple-600 border-purple-100', bar: 'bg-purple-500', section: '' },
  { title: 'Digital Exams', description: 'Take available online exams.', to: '/student/exams/digital', icon: Monitor, roles: ['STUDENT'], badge: 'bg-sky-50 text-sky-600 border-sky-100', bar: 'bg-sky-500', section: '' },
  { title: 'My Attendance', description: 'View your attendance record by course.', to: '/sis/attendance/me', icon: CalendarCheck, roles: ['STUDENT'], badge: 'bg-amber-50 text-amber-600 border-amber-100', bar: 'bg-amber-500', section: '' },
  { title: 'My Marks', description: 'Review internal assessment marks.', to: '/sis/marks/me', icon: BookMarked, roles: ['STUDENT'], badge: 'bg-orange-50 text-orange-600 border-orange-100', bar: 'bg-orange-500', section: '' },
  { title: 'Hall Ticket', description: 'Check eligibility and download your hall ticket.', to: '/sis/hall-tickets/me', icon: Ticket, roles: ['STUDENT'], badge: 'bg-yellow-50 text-yellow-600 border-yellow-100', bar: 'bg-yellow-500', section: '' },
  { title: 'Exam Timetable', description: 'View your upcoming exam schedule.', to: '/sis/exam/my-timetable', icon: CalendarDays, roles: ['STUDENT'], badge: 'bg-red-50 text-red-600 border-red-100', bar: 'bg-red-500', section: '' },
  { title: 'My Transcript', description: 'View your semester-wise grade history.', to: '/sis/my-transcript', icon: Award, roles: ['STUDENT'], badge: 'bg-pink-50 text-pink-600 border-pink-100', bar: 'bg-pink-500', section: '' },
  { title: 'Notifications', description: 'See all your notifications.', to: '/notifications', icon: Bell, roles: ['STUDENT'], badge: 'bg-indigo-50 text-indigo-600 border-indigo-100', bar: 'bg-indigo-500', section: '' },
  { title: 'My Profile', description: 'Update your contact and personal details.', to: '/sis/me/profile', icon: UserCircle2, roles: ['STUDENT'], badge: 'bg-slate-50 text-slate-600 border-slate-100', bar: 'bg-slate-500', section: '' },
]

export function QuickActions() {
  const navigate = useNavigate()

  return (
    <section aria-labelledby="quick-actions-heading">
      <h2 id="quick-actions-heading" className="text-xs font-bold text-foreground uppercase tracking-widest mb-4">
        Quick Actions
      </h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {ACTIONS.map((card) => (
          <ModuleCardItem key={card.to} card={card} onClick={() => navigate(card.to)} />
        ))}
      </div>
    </section>
  )
}
