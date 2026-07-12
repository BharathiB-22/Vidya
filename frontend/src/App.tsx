import { useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthGuard } from '@/components/AuthGuard'
import { AdminAuthGuard } from '@/components/AdminAuthGuard'
import { AdminShell } from '@/components/admin/AdminShell'
import { AppShell } from '@/components/shell/AppShell'
import LoginPage from '@/pages/LoginPage'
import AdminLoginPage from '@/pages/AdminLoginPage'
import DashboardPage from '@/pages/DashboardPage'
import TenantListPage from '@/pages/admin/TenantListPage'
import TenantCreatePage from '@/pages/admin/TenantCreatePage'
import TenantDetailPage from '@/pages/admin/TenantDetailPage'
import AdminDashboardPage from '@/pages/admin/AdminDashboardPage'
import MonitoringPage from '@/pages/admin/MonitoringPage'
import AuditLogsPage from '@/pages/admin/AuditLogsPage'
import AdminSettingsPage from '@/pages/admin/SettingsPage'
import HealthPage from '@/pages/admin/HealthPage'
import ProfilePage from '@/pages/admin/ProfilePage'
import PlatformBrandingPage from '@/pages/admin/PlatformBrandingPage'
import DeletedTenantsPage from '@/pages/admin/DeletedTenantsPage'
import TenantMigrationsPage from '@/pages/admin/TenantMigrationsPage'
import ProgramListPage from '@/pages/ProgramListPage'
import ProgramDetailPage from '@/pages/ProgramDetailPage'
import GovernanceQueuePage from '@/pages/governance/GovernanceQueuePage'
import CurriculumWorkbenchPage from '@/pages/governance/CurriculumWorkbenchPage'
import ApprovedCurriculaPage from '@/pages/governance/ApprovedCurriculaPage'
import SyllabusListPage from '@/pages/SyllabusListPage'
import SyllabusDetailPage from '@/pages/SyllabusDetailPage'
import CourseKitListPage from '@/pages/CourseKitListPage'
import CourseKitDetailPage from '@/pages/CourseKitDetailPage'
import LearningPackageListPage from '@/pages/LearningPackageListPage'
import LearningPackagePage from '@/pages/LearningPackage'
import FacultyCuratePage from '@/pages/FacultyCurate'
import LabAssignmentListPage from '@/pages/LabAssignmentListPage'
import LabAssignmentDetailPage from '@/pages/LabAssignmentDetailPage'
import LabReviewPanel from '@/pages/LabReviewPanel'
import StudentLabListPage from '@/pages/StudentLabListPage'
import StudentSubmitPage from '@/pages/StudentSubmitPage'
import StudentResultPage from '@/pages/StudentResultPage'
import ResearchProblemListPage from '@/pages/ResearchProblemListPage'
import ResearchProblemDetailPage from '@/pages/ResearchProblemDetailPage'
import ResearchDocumentPage from '@/pages/ResearchDocumentPage'
import VivaRatifyPage from '@/pages/VivaRatifyPage'
import StudentResearchPage from '@/pages/StudentResearchPage'
import StudentResearchDetailPage from '@/pages/StudentResearchDetailPage'
import StudentVivaPage from '@/pages/StudentVivaPage'
import MySubjectsPage from '@/pages/student/MySubjectsPage'
import SubjectDetailsPage from '@/pages/student/SubjectDetailsPage'
import CalendarPage from '@/pages/student/CalendarPage'
import ElectivesPage from '@/pages/student/ElectivesPage'
import CourseKitsPage from '@/pages/student/CourseKitsPage'
import LearningMaterialsPage from '@/pages/student/LearningMaterialsPage'
import SemesterResultsPage from '@/pages/student/SemesterResultsPage'
import EventsPage from '@/pages/student/EventsPage'
import AcademicProgressPage from '@/pages/student/AcademicProgressPage'
import StudentTimetablePage from '@/pages/student/TimetablePage'
import FacultyTimetablePage from '@/pages/FacultyTimetablePage'
import TimetableBuilderPage from '@/pages/dean/TimetableBuilderPage'
import CourseKitCompliancePage from '@/pages/dean/CourseKitCompliancePage'
import StudentAssignmentListPage from '@/pages/coursework/StudentAssignmentListPage'
import StudentAssignmentSubmitPage from '@/pages/coursework/StudentAssignmentSubmitPage'
import StudentAssignmentResultPage from '@/pages/coursework/StudentAssignmentResultPage'
import FacultyAssignmentListPage from '@/pages/coursework/FacultyAssignmentListPage'
import FacultyAssignmentFormPage from '@/pages/coursework/FacultyAssignmentFormPage'
import FacultyAssignmentGradingPage from '@/pages/coursework/FacultyAssignmentGradingPage'
import ExamPaperListPage from '@/pages/ExamPaperListPage'
import ExamPaperCreatePage from '@/pages/ExamPaperCreatePage'
import ExamPaperEditorPage from '@/pages/ExamPaperEditorPage'
import BoardReviewPage from '@/pages/BoardReviewPage'
import InternalExamReleasePage from '@/pages/InternalExamReleasePage'
import ScriptListPage from '@/pages/ScriptListPage'
import ScriptUploadPage from '@/pages/ScriptUploadPage'
import ScriptEvaluationPanel from '@/pages/ScriptEvaluationPanel'
import BoardScriptReviewPage from '@/pages/BoardScriptReviewPage'
import DoubleEvaluationComparisonPage from '@/pages/DoubleEvaluationComparisonPage'
import MyScriptsPage from '@/pages/MyScriptsPage'
import ScoreLedgerPage from '@/pages/ScoreLedgerPage'
import BellCurveListPage from '@/pages/BellCurveListPage'
import BellCurveAnalysisPage from '@/pages/BellCurveAnalysisPage'
import BellCurveRatifyPage from '@/pages/BellCurveRatifyPage'
import FairnessReportPage from '@/pages/FairnessReportPage'
import FirstLoginPage from '@/pages/FirstLoginPage'
import ForgotPasswordPage from '@/pages/ForgotPasswordPage'
import UsersPage from '@/pages/UsersPage'
import BulkOnboardingPage from '@/pages/BulkOnboardingPage'
import SettingsPage from '@/pages/SettingsPage'
import InstitutionAdminProfilePage from '@/pages/InstitutionAdminProfilePage'
import SettingsBrandingPage from '@/pages/SettingsBrandingPage'
import EvaluatorDashboardPage from '@/pages/EvaluatorDashboardPage'
import EvaluatorSubmissionsPage from '@/pages/EvaluatorSubmissionsPage'
import EvaluatorReviewPanel from '@/pages/EvaluatorReviewPanel'
import MyCoursesPage from '@/pages/MyCoursesPage'
import FacultySubjectWorkspacePage from '@/pages/faculty/subjects/FacultySubjectWorkspacePage'
import DepartmentsPage from '@/pages/academics/DepartmentsPage'
import ProgramsPage from '@/pages/academics/ProgramsPage'
import BatchesPage from '@/pages/academics/BatchesPage'
import SectionsPage from '@/pages/academics/SectionsPage'
import SemestersPage from '@/pages/academics/SemestersPage'
import SchoolsPage from '@/pages/sis/SchoolsPage'
import SisDepartmentsPage from '@/pages/sis/DepartmentsPage'
import SisDashboardPage from '@/pages/sis/SisDashboardPage'
import RosterPage from '@/pages/sis/RosterPage'
import StudentProfilePage from '@/pages/sis/StudentProfilePage'
import StudentDirectoryPage from '@/pages/sis/StudentDirectoryPage'
import FacultyDirectoryPage from '@/pages/sis/FacultyDirectoryPage'
import FacultyProfilePage from '@/pages/sis/FacultyProfilePage'
import GovernanceDirectoryPage from '@/pages/sis/GovernanceDirectoryPage'
import DeanMyFacultyPage from '@/pages/dean/DeanMyFacultyPage'
import DeanMyStudentsPage from '@/pages/dean/DeanMyStudentsPage'
import AcademicOwnershipPage from '@/pages/dean/AcademicOwnershipPage'
import FacultyResponsibilitiesPage from '@/pages/faculty/FacultyResponsibilitiesPage'
import FacultyElectiveStudentsPage from '@/pages/faculty/ElectiveStudentsPage'
import NotificationCenterPage from '@/pages/NotificationCenterPage'
import MyProfilePage from '@/pages/sis/MyProfilePage'
import SemesterRolloverPage from '@/pages/sis/SemesterRolloverPage'
import ImportHistoryPage from '@/pages/sis/ImportHistoryPage'
import CapacityPage from '@/pages/sis/CapacityPage'
import ValidationReportPage from '@/pages/sis/ValidationReportPage'
import FacultyAttendanceDashboard from '@/pages/sis/attendance/FacultyAttendanceDashboard'
import TakeAttendancePage from '@/pages/sis/attendance/TakeAttendancePage'
import StudentAttendancePage from '@/pages/student/StudentAttendancePage'
import AttendanceAnalyticsPage from '@/pages/sis/AttendanceAnalyticsPage'
import FacultyShortageReportPage from '@/pages/sis/FacultyShortageReportPage'
import InternalMarksSetupPage from '@/pages/sis/InternalMarksSetupPage'
import InternalMarkEntryPage from '@/pages/sis/InternalMarkEntryPage'
import InternalMarksReportPage from '@/pages/sis/InternalMarksReportPage'
import MyMarksPage from '@/pages/sis/MyMarksPage'
import ResultDeclarationsListPage from '@/pages/sis/ResultDeclarationsListPage'
import ResultDeclarationDetailPage from '@/pages/sis/ResultDeclarationDetailPage'
import ResultVerifyPage from '@/pages/sis/ResultVerifyPage'
import GradeCardPage from '@/pages/sis/GradeCardPage'
import RankListPage from '@/pages/sis/RankListPage'
import MyGradeCardPage from '@/pages/sis/MyGradeCardPage'
import MyTranscriptPage from '@/pages/sis/MyTranscriptPage'
import HallTicketDashboardPage from '@/pages/sis/HallTicketDashboardPage'
import EligibilityDetailPage from '@/pages/sis/EligibilityDetailPage'
import MyHallTicketPage from '@/pages/sis/MyHallTicketPage'
import ExamCentersPage from '@/pages/sis/ExamCentersPage'
import ExamSessionsPage from '@/pages/sis/ExamSessionsPage'
import ExamSessionDetailPage from '@/pages/sis/ExamSessionDetailPage'
import ExamInvigilationPage from '@/pages/sis/ExamInvigilationPage'
import ExamSeatAllocationPage from '@/pages/sis/ExamSeatAllocationPage'
import MyExamTimetablePage from '@/pages/sis/MyExamTimetablePage'
import AvailableExamsPage from '@/pages/student/AvailableExamsPage'
import ExamInstructionsPage from '@/pages/student/ExamInstructionsPage'
import ActiveExamPage from '@/pages/student/ActiveExamPage'
import SubmissionConfirmPage from '@/pages/student/SubmissionConfirmPage'
import ExamResultPage from '@/pages/student/ExamResultPage'
import { ExamGuard } from '@/components/digitalExams/ExamGuard'
import DigitalSessionsPage from '@/pages/DigitalSessionsPage'
import CreateDigitalSessionPage from '@/pages/CreateDigitalSessionPage'
import DigitalSessionDetailPage from '@/pages/DigitalSessionDetailPage'
import DigitalMonitoringPage from '@/pages/DigitalMonitoringPage'
import DeanDigitalAnalyticsPage from '@/pages/DeanDigitalAnalyticsPage'
import SessionStatisticsPage from '@/pages/SessionStatisticsPage'
import DeanExamAnalyticsPage from '@/pages/DeanExamAnalyticsPage'
import AdminExamAnalyticsPage from '@/pages/AdminExamAnalyticsPage'
import BoardExamAnalyticsPage from '@/pages/BoardExamAnalyticsPage'
import AdminCompliancePage from '@/pages/AdminCompliancePage'
import BoardCompliancePage from '@/pages/BoardCompliancePage'
import SubjectiveReviewQueuePage from '@/pages/SubjectiveReviewQueuePage'
import SubjectiveReviewPage from '@/pages/SubjectiveReviewPage'
import OCRReviewQueuePage from '@/pages/OCRReviewQueuePage'
import OCRReviewDetailPage from '@/pages/OCRReviewDetailPage'
import FacultyAssignmentsPage from '@/pages/assignments/FacultyAssignmentsPage'
import FacultyAssignmentDetailPage from '@/pages/assignments/FacultyAssignmentDetailPage'
import AssignmentManagementPage from '@/pages/assignments/AssignmentManagementPage'
import { useAuth } from '@/lib/auth'
import { useBranding } from '@/lib/branding'

export default function App() {
  const { isAuthenticated } = useAuth()
  const { fetchBranding, clearBranding } = useBranding()

  useEffect(() => {
    if (isAuthenticated) {
      fetchBranding()
    } else {
      clearBranding()
    }
  }, [isAuthenticated]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />

      {/* Super Admin portal — separate auth context */}
      <Route path="/admin/login" element={<AdminLoginPage />} />
      <Route element={<AdminAuthGuard />}>
        <Route element={<AdminShell />}>
          <Route path="/admin/dashboard" element={<AdminDashboardPage />} />
          <Route path="/admin/tenants" element={<TenantListPage />} />
          <Route path="/admin/tenants/new" element={<TenantCreatePage />} />
          <Route path="/admin/tenants/:id" element={<TenantDetailPage />} />
          <Route path="/admin/monitoring"        element={<MonitoringPage />} />
          <Route path="/admin/audit-logs"       element={<AuditLogsPage />} />
          <Route path="/admin/settings"         element={<AdminSettingsPage />} />
          <Route path="/admin/health"           element={<HealthPage />} />
          <Route path="/admin/profile"          element={<ProfilePage />} />
          <Route path="/admin/branding"         element={<PlatformBrandingPage />} />
          <Route path="/admin/deleted-tenants"    element={<DeletedTenantsPage />} />
          <Route path="/admin/tenant-migrations" element={<TenantMigrationsPage />} />
          <Route path="/admin" element={<Navigate to="/admin/dashboard" replace />} />
        </Route>
      </Route>

      {/* Tenant portal — auth gate → app shell → role gates */}
      <Route element={<AuthGuard />}>
        {/* Standalone first-login page — no shell, blocks access until password is set */}
        <Route path="/first-login" element={<FirstLoginPage />} />

        <Route element={<AppShell />}>

          {/* Dashboard — all authenticated roles */}
          <Route path="/dashboard" element={<DashboardPage />} />

          {/* DEAN pages */}
          <Route element={<AuthGuard allowedRoles={['DEAN', 'ADMIN']} />}>
            <Route path="/dean/academic-ownership" element={<AcademicOwnershipPage />} />
            {/* Syllabus Review merged into the unified Syllabuses page (tabbed by
                status). Old link redirects so bookmarks keep working. */}
            <Route path="/dean-review"             element={<Navigate to="/syllabuses" replace />} />
            <Route path="/dean/course-kit-compliance"   element={<CourseKitCompliancePage />} />
          </Route>

          {/* Timetable — DEAN owns the class timetable end-to-end (create, assign
              faculty/subject/room, save draft, review, publish). ADMIN has no access.
              Single merged page: Templates / Draft / Pending Review / Published / Archive. */}
          <Route element={<AuthGuard allowedRoles={['DEAN']} />}>
            <Route path="/timetable"               element={<TimetableBuilderPage />} />
            <Route path="/timetable/builder"       element={<TimetableBuilderPage />} />
          </Route>

          {/* Dean department-scoped pages */}
          <Route element={<AuthGuard allowedRoles={['DEAN']} />}>
            <Route path="/dean/my-faculty"             element={<DeanMyFacultyPage />} />
            <Route path="/dean/my-students"            element={<DeanMyStudentsPage />} />
          </Route>

          {/* Faculty governance pages */}
          <Route element={<AuthGuard allowedRoles={['FACULTY']} />}>
            <Route path="/faculty/my-responsibilities" element={<FacultyResponsibilitiesPage />} />
            <Route path="/faculty/elective-students"   element={<FacultyElectiveStudentsPage />} />
          </Route>

          {/* Notifications — STUDENT, FACULTY (student UI already links here) */}
          <Route element={<AuthGuard allowedRoles={['STUDENT', 'FACULTY']} />}>
            <Route path="/notifications" element={<NotificationCenterPage />} />
          </Route>

          {/* Dean Digital Exam Analytics — DEAN, ADMIN, BOARD */}
          <Route element={<AuthGuard allowedRoles={['DEAN', 'ADMIN', 'BOARD']} />}>
            <Route path="/exams/digital/analytics"              element={<DeanDigitalAnalyticsPage />} />
            <Route path="/exams/digital/analytics/:sessionId"   element={<SessionStatisticsPage />} />
          </Route>

          {/* M09.8 Examination Analytics — role-specific dashboards */}
          <Route element={<AuthGuard allowedRoles={['DEAN', 'ADMIN']} />}>
            <Route path="/dean/exam-analytics" element={<DeanExamAnalyticsPage />} />
          </Route>
          <Route element={<AuthGuard allowedRoles={['ADMIN']} />}>
            <Route path="/admin/exam-analytics" element={<AdminExamAnalyticsPage />} />
          </Route>
          <Route element={<AuthGuard allowedRoles={['BOARD', 'ADMIN', 'DEAN']} />}>
            <Route path="/board/exam-analytics" element={<BoardExamAnalyticsPage />} />
          </Route>

          {/* M09.9 Compliance & Audit — governance dashboards */}
          <Route element={<AuthGuard allowedRoles={['ADMIN', 'DEAN']} />}>
            <Route path="/admin/compliance" element={<AdminCompliancePage />} />
          </Route>
          <Route element={<AuthGuard allowedRoles={['BOARD', 'ADMIN', 'DEAN']} />}>
            <Route path="/board/compliance" element={<BoardCompliancePage />} />
          </Route>

          {/* My Courses — FACULTY only */}
          <Route element={<AuthGuard allowedRoles={['FACULTY']} />}>
            <Route path="/my-courses" element={<MyCoursesPage />} />
            <Route path="/faculty/subjects/:assignmentId" element={<FacultySubjectWorkspacePage />} />
          </Route>

          {/* Academic structure — ADMIN only (infrastructure, not academic decisions) */}
          <Route element={<AuthGuard allowedRoles={['ADMIN']} />}>
            <Route path="/academics/departments" element={<DepartmentsPage />} />
            <Route path="/academics/programs"    element={<ProgramsPage />} />
            <Route path="/academics/semesters"   element={<SemestersPage />} />
            <Route path="/academics/batches"     element={<BatchesPage />} />
            <Route path="/academics/sections"    element={<SectionsPage />} />
          </Route>

          {/* SIS — ADMIN only */}
          <Route element={<AuthGuard allowedRoles={['ADMIN']} />}>
            <Route path="/sis"                                   element={<SisDashboardPage />} />
            <Route path="/sis/roster"                            element={<RosterPage />} />
            <Route path="/sis/schools"                           element={<SchoolsPage />} />
            <Route path="/sis/departments"                       element={<SisDepartmentsPage />} />
            <Route path="/sis/directory/students"                element={<StudentDirectoryPage />} />
          </Route>
          {/* Student profile — ADMIN + DEAN (Dean reaches it from My Students) */}
          <Route element={<AuthGuard allowedRoles={['ADMIN', 'DEAN']} />}>
            <Route path="/sis/students/:student_id"              element={<StudentProfilePage />} />
            <Route path="/sis/directory/students/:student_id"    element={<StudentProfilePage />} />
          </Route>

          {/* SIS Semester Rollover + Import History — ADMIN only */}
          <Route element={<AuthGuard allowedRoles={['ADMIN']} />}>
            <Route path="/sis/rollover" element={<SemesterRolloverPage />} />
            <Route path="/sis/imports" element={<ImportHistoryPage />} />
            <Route path="/sis/capacity" element={<CapacityPage />} />
            <Route path="/sis/validation" element={<ValidationReportPage />} />
          </Route>

          {/* Attendance — Faculty: today's classes dashboard + take-attendance + shortage */}
          <Route element={<AuthGuard allowedRoles={['FACULTY']} />}>
            <Route path="/sis/attendance" element={<FacultyAttendanceDashboard />} />
            <Route path="/sis/attendance/take" element={<TakeAttendancePage />} />
            <Route path="/sis/attendance/shortage" element={<FacultyShortageReportPage />} />
          </Route>

          {/* Attendance analytics — Dean only */}
          <Route element={<AuthGuard allowedRoles={['DEAN']} />}>
            <Route path="/sis/attendance/analytics" element={<AttendanceAnalyticsPage />} />
          </Route>

          {/* Attendance — Student self-view (read-only) */}
          <Route element={<AuthGuard allowedRoles={['STUDENT']} />}>
            <Route path="/sis/attendance/me" element={<StudentAttendancePage />} />
          </Route>

          {/* Internal Marks — Faculty */}
          <Route element={<AuthGuard allowedRoles={['FACULTY']} />}>
            <Route path="/sis/marks/setup"          element={<InternalMarksSetupPage />} />
            <Route path="/sis/marks/entry/:componentId" element={<InternalMarkEntryPage />} />
          </Route>

          {/* Internal Marks report — Dean only */}
          <Route element={<AuthGuard allowedRoles={['DEAN']} />}>
            <Route path="/sis/marks/report" element={<InternalMarksReportPage />} />
          </Route>

          {/* Internal Marks — Student self-view */}
          <Route element={<AuthGuard allowedRoles={['STUDENT']} />}>
            <Route path="/sis/marks/me" element={<MyMarksPage />} />
          </Route>

          {/* Results — Dean owns; Admin has read-only access */}
          <Route element={<AuthGuard allowedRoles={['DEAN', 'ADMIN']} />}>
            <Route path="/sis/results"                     element={<ResultDeclarationsListPage />} />
            <Route path="/sis/results/:id"                 element={<ResultDeclarationDetailPage />} />
            <Route path="/sis/results/:id/grade-cards"     element={<GradeCardPage />} />
          </Route>

          {/* Results Verify/Approve — Dean only; Admin cannot approve results */}
          <Route element={<AuthGuard allowedRoles={['DEAN']} />}>
            <Route path="/sis/results/:id/verify"          element={<ResultVerifyPage />} />
          </Route>

          {/* Rank List — Dean, Faculty */}
          <Route element={<AuthGuard allowedRoles={['DEAN', 'FACULTY']} />}>
            <Route path="/sis/results/:id/ranks"           element={<RankListPage />} />
          </Route>

          {/* Student Results — STUDENT only */}
          <Route element={<AuthGuard allowedRoles={['STUDENT']} />}>
            <Route path="/sis/my-grade-card/:declId"       element={<MyGradeCardPage />} />
            <Route path="/sis/my-transcript"               element={<MyTranscriptPage />} />
          </Route>

          {/* Hall Ticket Management — Dean only */}
          <Route element={<AuthGuard allowedRoles={['DEAN']} />}>
            <Route path="/sis/hall-tickets"                element={<HallTicketDashboardPage />} />
            <Route path="/sis/hall-tickets/:id"            element={<EligibilityDetailPage />} />
          </Route>

          {/* Hall Ticket — STUDENT self-service */}
          <Route element={<AuthGuard allowedRoles={['STUDENT']} />}>
            <Route path="/sis/hall-tickets/me"             element={<MyHallTicketPage />} />
          </Route>

          {/* Exam Management — Dean only */}
          <Route element={<AuthGuard allowedRoles={['DEAN']} />}>
            <Route path="/sis/exam/centers"                       element={<ExamCentersPage />} />
            <Route path="/sis/exam/sessions"                      element={<ExamSessionsPage />} />
            <Route path="/sis/exam/sessions/:id"                  element={<ExamSessionDetailPage />} />
            <Route path="/sis/exam/sessions/:id/invigilation"     element={<ExamInvigilationPage />} />
            <Route path="/sis/exam/sessions/:id/seats"            element={<ExamSeatAllocationPage />} />
          </Route>

          {/* Student Exam Timetable — STUDENT */}
          <Route element={<AuthGuard allowedRoles={['STUDENT']} />}>
            <Route path="/sis/exam/my-timetable"           element={<MyExamTimetablePage />} />
          </Route>

          {/* Digital Exams — M09.5 Student flow */}
          <Route element={<AuthGuard allowedRoles={['STUDENT']} />}>
            <Route path="/student/exams/digital"                        element={<AvailableExamsPage />} />
            <Route element={<ExamGuard />}>
              <Route path="/student/exams/digital/:sessionId/instructions" element={<ExamInstructionsPage />} />
              <Route path="/student/exams/digital/:sessionId/take"         element={<ActiveExamPage />} />
              <Route path="/student/exams/digital/:sessionId/submitted"    element={<SubmissionConfirmPage />} />
            </Route>
            <Route path="/student/exams/digital/attempts/:attemptId/result" element={<ExamResultPage />} />
          </Route>

          {/* SIS Faculty Directory — ADMIN only (Deans use /dean/my-faculty) */}
          <Route element={<AuthGuard allowedRoles={['ADMIN']} />}>
            <Route path="/sis/directory/faculty"          element={<FacultyDirectoryPage />} />
            <Route path="/sis/governance"                 element={<GovernanceDirectoryPage />} />
          </Route>
          {/* Faculty profile detail — ADMIN + DEAN (Dean reaches it from My Faculty) */}
          <Route element={<AuthGuard allowedRoles={['ADMIN', 'DEAN']} />}>
            <Route path="/sis/directory/faculty/:user_id" element={<FacultyProfilePage />} />
          </Route>

          {/* User management & settings — ADMIN only */}
          <Route element={<AuthGuard allowedRoles={['ADMIN']} />}>
            <Route path="/users" element={<UsersPage />} />
            <Route path="/users/bulk-onboarding" element={<BulkOnboardingPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/settings/branding" element={<SettingsBrandingPage />} />
            <Route path="/my-profile" element={<InstitutionAdminProfilePage />} />
          </Route>

          {/* Curriculum — the Dean PREPARES it here; the governance authority
              (BOARD) reviews and approves the same pages. What each role may DO
              is decided per-status by the API and by ActionBar, not by the route:
              a Dean cannot edit a submitted curriculum, and a Board member cannot
              edit one that is still a draft. */}
          <Route element={<AuthGuard allowedRoles={['DEAN', 'ADMIN', 'BOARD']} />}>
            <Route path="/programs" element={<ProgramListPage />} />
            <Route path="/programs/:id" element={<ProgramDetailPage />} />
          </Route>

          {/* Academic Governance — BOARD only (Phase A). A Dean is deliberately
              excluded: they must never approve curriculum they prepared.

              The Workbench is where the Board actually works: it writes the
              official syllabus for every subject there and approves from there. */}
          <Route element={<AuthGuard allowedRoles={['BOARD']} />}>
            <Route path="/governance/curriculum" element={<GovernanceQueuePage />} />
            <Route path="/governance/curriculum/:programId" element={<CurriculumWorkbenchPage />} />
            <Route path="/governance/approved"   element={<ApprovedCurriculaPage />} />
          </Route>

          {/* Teach & Prepare — FACULTY, DEAN, ADMIN, and BOARD.
              Phase A: the syllabus is curriculum, so the governance authority
              WRITES it and Faculty read it. Write access is enforced by the API
              (m02 _WRITE = ADMIN + BOARD); the route just lets them all look. */}
          <Route element={<AuthGuard allowedRoles={['FACULTY', 'DEAN', 'ADMIN', 'BOARD']} />}>
            <Route path="/syllabuses" element={<SyllabusListPage />} />
            <Route path="/syllabuses/:id" element={<SyllabusDetailPage />} />
            <Route path="/course-kits" element={<CourseKitListPage />} />
            <Route path="/course-kits/:id" element={<CourseKitDetailPage />} />
            <Route path="/learning-packages" element={<LearningPackageListPage />} />
            <Route path="/learning-packages/:id" element={<LearningPackagePage />} />
            <Route path="/learning-packages/:id/curate" element={<FacultyCuratePage />} />
          </Route>

          {/* Lab Assignments — FACULTY, ADMIN */}
          <Route element={<AuthGuard allowedRoles={['FACULTY', 'ADMIN']} />}>
            <Route path="/labs" element={<LabAssignmentListPage />} />
            <Route path="/labs/review/:submissionId" element={<LabReviewPanel />} />
            <Route path="/labs/:id" element={<LabAssignmentDetailPage />} />
            <Route path="/faculty/timetable" element={<FacultyTimetablePage />} />
          </Route>

          {/* Coursework Assignments (theory/essay/report — distinct from Labs) — FACULTY, ADMIN */}
          <Route element={<AuthGuard allowedRoles={['FACULTY', 'ADMIN']} />}>
            <Route path="/faculty/assignments" element={<FacultyAssignmentListPage />} />
            <Route path="/faculty/assignments/new" element={<FacultyAssignmentFormPage />} />
            <Route path="/faculty/assignments/:id/edit" element={<FacultyAssignmentFormPage />} />
            <Route path="/faculty/assignments/:id/submissions" element={<FacultyAssignmentGradingPage />} />
          </Route>

          {/* Evaluator area — EVALUATOR only */}
          <Route element={<AuthGuard allowedRoles={['EVALUATOR']} />}>
            <Route path="/evaluator" element={<EvaluatorDashboardPage />} />
            <Route path="/evaluator/:assignmentId/submissions" element={<EvaluatorSubmissionsPage />} />
            <Route path="/evaluator/submissions/:submissionId" element={<EvaluatorReviewPanel />} />
          </Route>

          {/* Student area — STUDENT, ADMIN */}
          <Route element={<AuthGuard allowedRoles={['STUDENT', 'ADMIN']} />}>
            <Route path="/student/labs" element={<StudentLabListPage />} />
            <Route path="/student/labs/:id" element={<StudentSubmitPage />} />
            <Route path="/student/submissions/:submissionId/result" element={<StudentResultPage />} />
            <Route path="/student/research" element={<StudentResearchPage />} />
            <Route path="/student/research/:id" element={<StudentResearchDetailPage />} />
            <Route path="/student/viva/:token" element={<StudentVivaPage />} />
            <Route path="/student/subjects" element={<MySubjectsPage />} />
            <Route path="/student/subjects/:courseId" element={<SubjectDetailsPage />} />
            <Route path="/student/assignments" element={<StudentAssignmentListPage />} />
            <Route path="/student/assignments/:id" element={<StudentAssignmentSubmitPage />} />
            <Route path="/student/assignment-submissions/:submissionId/result" element={<StudentAssignmentResultPage />} />
            <Route path="/student/calendar" element={<CalendarPage />} />
            <Route path="/student/electives" element={<ElectivesPage />} />
            <Route path="/student/course-kits" element={<CourseKitsPage />} />
            <Route path="/student/learning-materials" element={<LearningMaterialsPage />} />
            <Route path="/student/semester-results" element={<SemesterResultsPage />} />
            <Route path="/student/events" element={<EventsPage />} />
            <Route path="/student/academic-progress" element={<AcademicProgressPage />} />
            <Route path="/student/timetable" element={<StudentTimetablePage />} />
          </Route>

          {/* Self-service profile — STUDENT, FACULTY, DEAN */}
          <Route element={<AuthGuard allowedRoles={['STUDENT', 'FACULTY', 'DEAN']} />}>
            <Route path="/sis/me/profile" element={<MyProfilePage />} />
          </Route>

          {/* Research Supervision / Guide Assignments — FACULTY, ADMIN, GUIDE, DEAN */}
          <Route element={<AuthGuard allowedRoles={['FACULTY', 'ADMIN', 'GUIDE', 'DEAN']} />}>
            <Route path="/research/problems" element={<ResearchProblemListPage />} />
            <Route path="/research/problems/:problemId" element={<ResearchProblemDetailPage />} />
            <Route path="/research/documents/:id" element={<ResearchDocumentPage />} />
            <Route path="/research/vivas/:id" element={<VivaRatifyPage />} />
            {/* Bare paths have no content — redirect to the list page */}
            <Route path="/research" element={<Navigate to="/research/problems" replace />} />
            <Route path="/research/documents" element={<Navigate to="/research/problems" replace />} />
          </Route>

          {/* Exam Papers — FACULTY, ADMIN, BOARD */}
          <Route element={<AuthGuard allowedRoles={['FACULTY', 'ADMIN', 'BOARD']} />}>
            <Route path="/exams" element={<ExamPaperListPage />} />
            <Route path="/exams/create" element={<ExamPaperCreatePage />} />
            <Route path="/exams/board/pending" element={<ExamPaperListPage />} />
            <Route path="/exams/:id" element={<ExamPaperEditorPage />} />
            <Route path="/exams/:id/review" element={<BoardReviewPage />} />
          </Route>

          {/* Internal Marks — FACULTY, DEAN, ADMIN */}
          <Route element={<AuthGuard allowedRoles={['FACULTY', 'DEAN', 'ADMIN']} />}>
            <Route path="/exams/internal-marks" element={<InternalExamReleasePage />} />
            <Route path="/exams/internal-marks/course/:courseId" element={<InternalExamReleasePage />} />
          </Route>

          {/* Digital Exam Sessions — Dean owns; Admin + Board can view */}
          <Route element={<AuthGuard allowedRoles={['DEAN', 'ADMIN', 'BOARD']} />}>
            <Route path="/exams/digital"            element={<DigitalSessionsPage />} />
            <Route path="/exams/digital/monitoring" element={<DigitalMonitoringPage />} />
            <Route path="/exams/digital/:sessionId" element={<DigitalSessionDetailPage />} />
          </Route>
          {/* Digital session creation — Dean + Board only; Admin cannot create sessions */}
          <Route element={<AuthGuard allowedRoles={['DEAN', 'BOARD']} />}>
            <Route path="/exams/digital/create" element={<CreateDigitalSessionPage />} />
          </Route>

          {/* Scanned Scripts — ADMIN, BOARD */}
          <Route element={<AuthGuard allowedRoles={['ADMIN', 'BOARD']} />}>
            <Route path="/scripts" element={<ScriptListPage />} />
            <Route path="/scripts/upload" element={<ScriptUploadPage />} />
            <Route path="/scripts/board" element={<BoardScriptReviewPage />} />
            <Route path="/scripts/ledger" element={<ScoreLedgerPage />} />
            <Route path="/scripts/:scriptId/comparison" element={<DoubleEvaluationComparisonPage />} />
          </Route>

          {/* Script evaluation panel — FACULTY (assigned evaluator) + ADMIN + BOARD */}
          <Route element={<AuthGuard allowedRoles={['FACULTY', 'ADMIN', 'BOARD']} />}>
            <Route path="/scripts/:scriptId/evaluate" element={<ScriptEvaluationPanel />} />
          </Route>

          {/* My Scripts — FACULTY evaluator view */}
          <Route element={<AuthGuard allowedRoles={['FACULTY']} />}>
            <Route path="/scripts/evaluator" element={<MyScriptsPage />} />
          </Route>

          {/* Evaluation Assignments (M09.6) — Faculty / Evaluator own work */}
          <Route element={<AuthGuard allowedRoles={['FACULTY', 'EVALUATOR']} />}>
            <Route path="/faculty/evaluation-assignments"     element={<FacultyAssignmentsPage />} />
            <Route path="/faculty/evaluation-assignments/:id" element={<FacultyAssignmentDetailPage />} />
          </Route>

          {/* Evaluation Assignments (M09.6) — Admin management */}
          <Route element={<AuthGuard allowedRoles={['ADMIN']} />}>
            <Route path="/admin/evaluation-assignments" element={<AssignmentManagementPage mode="admin" />} />
          </Route>

          {/* Evaluation Assignments (M09.6) — Dean monitoring */}
          <Route element={<AuthGuard allowedRoles={['DEAN', 'ADMIN']} />}>
            <Route path="/dean/evaluation-assignments" element={<AssignmentManagementPage mode="dean" />} />
          </Route>

          {/* Digital Subjective Review — FACULTY, ADMIN */}
          <Route element={<AuthGuard allowedRoles={['FACULTY', 'ADMIN']} />}>
            <Route path="/faculty/digital-reviews"            element={<SubjectiveReviewQueuePage />} />
            <Route path="/faculty/digital-reviews/:attemptId" element={<SubjectiveReviewPage />} />
          </Route>

          {/* M09.7 OCR Review Queue — Dean owns; Faculty as assigned reviewers */}
          <Route element={<AuthGuard allowedRoles={['DEAN', 'FACULTY']} />}>
            <Route path="/ocr-review"           element={<OCRReviewQueuePage />} />
            <Route path="/ocr-review/:queueId"  element={<OCRReviewDetailPage />} />
          </Route>

          {/* Bell Curve — DEAN, ADMIN, BOARD */}
          <Route element={<AuthGuard allowedRoles={['DEAN', 'ADMIN', 'BOARD']} />}>
            <Route path="/bell-curve" element={<BellCurveListPage />} />
            <Route path="/bell-curve/reports" element={<FairnessReportPage />} />
            <Route path="/bell-curve/:id/ratify" element={<BellCurveRatifyPage />} />
            <Route path="/bell-curve/:id" element={<BellCurveAnalysisPage />} />
          </Route>

          <Route path="/" element={<Navigate to="/dashboard" replace />} />
        </Route>
      </Route>
    </Routes>
  )
}
