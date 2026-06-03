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
import ProgramListPage from '@/pages/ProgramListPage'
import ProgramDetailPage from '@/pages/ProgramDetailPage'
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
import ExamPaperListPage from '@/pages/ExamPaperListPage'
import ExamPaperCreatePage from '@/pages/ExamPaperCreatePage'
import ExamPaperEditorPage from '@/pages/ExamPaperEditorPage'
import BoardReviewPage from '@/pages/BoardReviewPage'
import InternalExamReleasePage from '@/pages/InternalExamReleasePage'
import ScriptListPage from '@/pages/ScriptListPage'
import ScriptUploadPage from '@/pages/ScriptUploadPage'
import ScriptEvaluationPanel from '@/pages/ScriptEvaluationPanel'
import BoardScriptReviewPage from '@/pages/BoardScriptReviewPage'
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
import SettingsBrandingPage from '@/pages/SettingsBrandingPage'
import EvaluatorDashboardPage from '@/pages/EvaluatorDashboardPage'
import EvaluatorSubmissionsPage from '@/pages/EvaluatorSubmissionsPage'
import EvaluatorReviewPanel from '@/pages/EvaluatorReviewPanel'
import CourseAssignmentsPage from '@/pages/CourseAssignmentsPage'
import DeanReviewPage from '@/pages/DeanReviewPage'
import MyCoursesPage from '@/pages/MyCoursesPage'
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
import MyProfilePage from '@/pages/sis/MyProfilePage'
import SemesterRolloverPage from '@/pages/sis/SemesterRolloverPage'
import AttendanceMarkPage from '@/pages/sis/AttendanceMarkPage'
import AttendanceSummaryPage from '@/pages/sis/AttendanceSummaryPage'
import AttendanceAnalyticsPage from '@/pages/sis/AttendanceAnalyticsPage'
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
          <Route path="/admin/deleted-tenants"  element={<DeletedTenantsPage />} />
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
            <Route path="/course-assignments" element={<CourseAssignmentsPage />} />
            <Route path="/dean-review"        element={<DeanReviewPage />} />
          </Route>

          {/* My Courses — FACULTY only */}
          <Route element={<AuthGuard allowedRoles={['FACULTY']} />}>
            <Route path="/my-courses" element={<MyCoursesPage />} />
          </Route>

          {/* Academic structure — ADMIN only */}
          <Route element={<AuthGuard allowedRoles={['ADMIN']} />}>
            <Route path="/academics/departments" element={<DepartmentsPage />} />
            <Route path="/academics/programs"    element={<ProgramsPage />} />
            <Route path="/academics/semesters"   element={<SemestersPage />} />
            <Route path="/academics/batches"     element={<BatchesPage />} />
            <Route path="/academics/sections"    element={<SectionsPage />} />
          </Route>

          {/* SIS — ADMIN and DEAN */}
          <Route element={<AuthGuard allowedRoles={['ADMIN', 'DEAN']} />}>
            <Route path="/sis"                                   element={<SisDashboardPage />} />
            <Route path="/sis/roster"                            element={<RosterPage />} />
            <Route path="/sis/students/:student_id"              element={<StudentProfilePage />} />
            <Route path="/sis/schools"                           element={<SchoolsPage />} />
            <Route path="/sis/departments"                       element={<SisDepartmentsPage />} />
            <Route path="/sis/directory/students"                element={<StudentDirectoryPage />} />
            <Route path="/sis/directory/students/:student_id"    element={<StudentProfilePage />} />
          </Route>

          {/* SIS Semester Rollover — ADMIN only */}
          <Route element={<AuthGuard allowedRoles={['ADMIN']} />}>
            <Route path="/sis/rollover" element={<SemesterRolloverPage />} />
          </Route>

          {/* Attendance — Faculty mark */}
          <Route element={<AuthGuard allowedRoles={['FACULTY']} />}>
            <Route path="/sis/attendance/mark" element={<AttendanceMarkPage />} />
          </Route>

          {/* Attendance — Dean/Admin analytics */}
          <Route element={<AuthGuard allowedRoles={['ADMIN', 'DEAN']} />}>
            <Route path="/sis/attendance/analytics" element={<AttendanceAnalyticsPage />} />
          </Route>

          {/* Attendance — Student self-view */}
          <Route element={<AuthGuard allowedRoles={['STUDENT']} />}>
            <Route path="/sis/attendance/me" element={<AttendanceSummaryPage />} />
          </Route>

          {/* SIS Faculty Directory — ADMIN, DEAN, FACULTY (read-only for FACULTY) */}
          <Route element={<AuthGuard allowedRoles={['ADMIN', 'DEAN', 'FACULTY']} />}>
            <Route path="/sis/directory/faculty"                 element={<FacultyDirectoryPage />} />
            <Route path="/sis/directory/faculty/:user_id"        element={<FacultyProfilePage />} />
          </Route>

          {/* User management & settings — ADMIN only */}
          <Route element={<AuthGuard allowedRoles={['ADMIN']} />}>
            <Route path="/users" element={<UsersPage />} />
            <Route path="/users/bulk-onboarding" element={<BulkOnboardingPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/settings/branding" element={<SettingsBrandingPage />} />
          </Route>

          {/* Teach & Prepare — FACULTY, DEAN, ADMIN */}
          <Route element={<AuthGuard allowedRoles={['FACULTY', 'DEAN', 'ADMIN']} />}>
            <Route path="/programs" element={<ProgramListPage />} />
            <Route path="/programs/:id" element={<ProgramDetailPage />} />
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
          </Route>

          {/* Self-service profile — STUDENT and FACULTY */}
          <Route element={<AuthGuard allowedRoles={['STUDENT', 'FACULTY']} />}>
            <Route path="/sis/me/profile" element={<MyProfilePage />} />
          </Route>

          {/* Research Supervision — FACULTY, ADMIN, GUIDE */}
          <Route element={<AuthGuard allowedRoles={['FACULTY', 'ADMIN', 'GUIDE']} />}>
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

          {/* Scanned Scripts — ADMIN, BOARD */}
          <Route element={<AuthGuard allowedRoles={['ADMIN', 'BOARD']} />}>
            <Route path="/scripts" element={<ScriptListPage />} />
            <Route path="/scripts/upload" element={<ScriptUploadPage />} />
            <Route path="/scripts/board" element={<BoardScriptReviewPage />} />
            <Route path="/scripts/ledger" element={<ScoreLedgerPage />} />
          </Route>

          {/* Script evaluation panel — FACULTY (assigned evaluator) + ADMIN + BOARD */}
          <Route element={<AuthGuard allowedRoles={['FACULTY', 'ADMIN', 'BOARD']} />}>
            <Route path="/scripts/:scriptId/evaluate" element={<ScriptEvaluationPanel />} />
          </Route>

          {/* My Scripts — FACULTY evaluator view */}
          <Route element={<AuthGuard allowedRoles={['FACULTY']} />}>
            <Route path="/scripts/evaluator" element={<MyScriptsPage />} />
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
