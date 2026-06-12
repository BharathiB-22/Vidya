// M09.8 Examination Analytics — shared dashboard view.
//
// One configurable view powers the Dean, Admin and Board dashboards.  Each page
// passes the `sections` it wants; everything else (data fetching, loading/empty
// states, layout) is shared so the three dashboards stay consistent.
import { useState } from 'react'
import {
  BarChart2, Users, Award, TrendingUp, TrendingDown, CheckCircle2,
  XCircle, RefreshCw, GraduationCap, Scale, RotateCcw, Building2, Target,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { PageLoading } from '@/components/shared/PageLoading'
import { PageError } from '@/components/shared/PageError'
import {
  StatCard, SectionCard, EmptyState, BarList, GradeHistogram,
  PassFailBar, DonutChart,
} from '@/components/analytics/charts'
import {
  useExamDashboard, useExamSubjects, useExamBatches, useExamFaculty,
} from '@/hooks/examAnalytics/useExamAnalytics'
import type { SubjectStat } from '@/types/examAnalytics'

export type AnalyticsSection =
  | 'overview' | 'passfail' | 'grades' | 'subjects'
  | 'batches' | 'faculty' | 'revaluation' | 'moderation'

const GRADE_HEX: Record<string, string> = {
  'A+': '#10b981', 'A': '#22c55e', 'B+': '#84cc16', 'B': '#facc15',
  'C': '#fbbf24', 'D': '#fb923c', 'F': '#f87171',
}

const PASS_OPTIONS = [33, 35, 40, 45, 50] as const

function subjectLabel(s: SubjectStat): string {
  return s.course_code || s.exam_paper_title || s.course_title || 'Untitled'
}

export function ExamAnalyticsView({
  title, subtitle, icon = BarChart2, sections,
}: {
  title: string
  subtitle: string
  icon?: typeof BarChart2
  sections: AnalyticsSection[]
}) {
  const [passThreshold, setPassThreshold] = useState(40)
  const params = { pass_threshold_pct: passThreshold }

  const has = (s: AnalyticsSection) => sections.includes(s)

  const dash = useExamDashboard(params)
  const subjects = useExamSubjects(has('subjects') ? params : undefined)
  const batches = useExamBatches(has('batches') ? params : undefined)
  const faculty = useExamFaculty(has('faculty') ? params : undefined)

  if (dash.isLoading) return <PageLoading />
  if (dash.isError || !dash.data) return <PageError onRetry={dash.refetch} />

  const d = dash.data
  const o = d.overview
  const isFetching = dash.isFetching || subjects.isFetching || batches.isFetching || faculty.isFetching

  return (
    <PageShell>
      <PageHeader
        icon={icon}
        title={title}
        subtitle={subtitle}
        action={
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1.5 text-xs text-gray-500">
              <Target className="h-3.5 w-3.5" />
              Pass ≥
              <select
                className="border rounded-md px-1.5 py-1 text-xs bg-white"
                value={passThreshold}
                onChange={(e) => setPassThreshold(Number(e.target.value))}
              >
                {PASS_OPTIONS.map(p => <option key={p} value={p}>{p}%</option>)}
              </select>
            </div>
            <Button variant="outline" size="sm" onClick={() => dash.refetch()} disabled={isFetching}>
              <RefreshCw className={`h-4 w-4 mr-1.5 ${isFetching ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
          </div>
        }
      />

      <div className="max-w-5xl space-y-6">

        {/* KPI cards */}
        {has('overview') && (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <StatCard label="Students" value={o.total_students} sub={`${o.papers_count} paper(s)`}
              icon={Users} colorClass="border-indigo-100 bg-indigo-50 text-indigo-700" />
            <StatCard label="Appeared" value={o.appeared} sub={`${o.absent} absent`}
              icon={Building2} colorClass="border-sky-100 bg-sky-50 text-sky-700" />
            <StatCard label="Passed" value={o.pass_count}
              icon={CheckCircle2} colorClass="border-green-100 bg-green-50 text-green-700" />
            <StatCard label="Failed" value={o.fail_count}
              icon={XCircle} colorClass="border-red-100 bg-red-50 text-red-700" />
            <StatCard label="Pass %" value={o.pass_pct != null ? `${o.pass_pct}%` : '—'}
              icon={TrendingUp} colorClass="border-emerald-100 bg-emerald-50 text-emerald-700" />
            <StatCard label="Average" value={o.average_pct != null ? `${o.average_pct}%` : '—'}
              sub={o.highest_pct != null ? `high ${o.highest_pct}%` : undefined}
              icon={Award} colorClass="border-teal-100 bg-teal-50 text-teal-700" />
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

          {/* Pass / fail */}
          {has('passfail') && (
            <SectionCard title="Pass / Fail Outcome" subtitle={`Threshold ${o.pass_threshold_pct}%`} icon={Scale}>
              <PassFailBar passCount={o.pass_count} failCount={o.fail_count} />
            </SectionCard>
          )}

          {/* Grade distribution — histogram + donut */}
          {has('grades') && (
            <SectionCard title="Grade Distribution" subtitle={`${d.grades.total_scripts} graded scripts`} icon={GraduationCap}>
              <GradeHistogram buckets={d.grades.buckets} />
              <div className="pt-2 border-t border-gray-50">
                <DonutChart
                  centerLabel="scripts"
                  segments={d.grades.buckets
                    .filter(b => b.count > 0)
                    .map(b => ({ label: b.grade, value: b.count, colorHex: GRADE_HEX[b.grade] ?? '#94a3b8' }))}
                />
              </div>
            </SectionCard>
          )}
        </div>

        {/* Subject performance */}
        {has('subjects') && (
          <SectionCard title="Subject Performance" subtitle="Hardest subjects first (lowest average)" icon={TrendingDown}>
            {subjects.isLoading ? <EmptyState message="Loading…" /> : (
              <BarList
                items={(subjects.data?.subjects ?? []).map(s => ({
                  label: subjectLabel(s),
                  sublabel: `${s.count} scripts · pass ${s.pass_pct ?? 0}%`,
                  value: s.average ?? 0,
                  display: s.average != null ? `${s.average}%` : '—',
                  tone: (s.average ?? 0) >= o.pass_threshold_pct ? 'teal' : 'red',
                }))}
                max={100}
              />
            )}
          </SectionCard>
        )}

        {/* Batch analytics */}
        {has('batches') && (
          <SectionCard title="Batch Performance" subtitle="By admission year" icon={Users}>
            {batches.isLoading ? <EmptyState message="Loading…" /> : (
              <BarList
                items={(batches.data?.batches ?? []).map(b => ({
                  label: b.label,
                  sublabel: `${b.count} students · topper ${b.topper_pct ?? 0}%`,
                  value: b.pass_pct ?? 0,
                  display: `${b.pass_pct ?? 0}% pass`,
                  tone: 'indigo',
                }))}
                max={100}
              />
            )}
          </SectionCard>
        )}

        {/* Faculty analytics */}
        {has('faculty') && (
          <SectionCard
            title="Faculty / Evaluator Analytics"
            subtitle={faculty.data?.institution_avg_awarded_pct != null
              ? `Institution avg awarded: ${faculty.data.institution_avg_awarded_pct}%`
              : 'Evaluation workload & marking patterns'}
            icon={Users}
          >
            {faculty.isLoading ? <EmptyState message="Loading…" /> : (
              (faculty.data?.faculty.length ?? 0) === 0 ? <EmptyState /> : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-xs text-gray-400 border-b">
                        <th className="py-2 font-medium">Evaluator</th>
                        <th className="py-2 font-medium text-right">Scripts</th>
                        <th className="py-2 font-medium text-right">Avg awarded</th>
                        <th className="py-2 font-medium text-right">Turnaround</th>
                      </tr>
                    </thead>
                    <tbody>
                      {faculty.data!.faculty.map(f => {
                        const bench = faculty.data!.institution_avg_awarded_pct
                        const unusual = bench != null && f.average_awarded_pct != null &&
                          Math.abs(f.average_awarded_pct - bench) >= 15
                        return (
                          <tr key={f.evaluator_id} className="border-b border-gray-50">
                            <td className="py-2.5 text-gray-800">
                              {f.evaluator_name || f.evaluator_id.slice(0, 8)}
                            </td>
                            <td className="py-2.5 text-right text-gray-700">{f.scripts_evaluated}</td>
                            <td className={`py-2.5 text-right font-medium ${unusual ? 'text-amber-600' : 'text-gray-700'}`}>
                              {f.average_awarded_pct != null ? `${f.average_awarded_pct}%` : '—'}
                              {unusual && <span className="ml-1 text-[10px]">⚠</span>}
                            </td>
                            <td className="py-2.5 text-right text-gray-500">
                              {f.avg_turnaround_hours != null ? `${f.avg_turnaround_hours}h` : '—'}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                  <p className="text-[10px] text-gray-400 pt-2">
                    ⚠ marks evaluators whose average deviates ≥15% from the institution benchmark — advisory only.
                  </p>
                </div>
              )
            )}
          </SectionCard>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

          {/* Revaluation insights */}
          {has('revaluation') && (
            <SectionCard title="Revaluation Insights" subtitle="Post-publication mark reviews" icon={RotateCcw}>
              {d.revaluation.total_requests === 0 ? <EmptyState message="No revaluation requests" /> : (
                <>
                  <div className="grid grid-cols-2 gap-3">
                    <StatCard label="Requests" value={d.revaluation.total_requests} sub={`${d.revaluation.pending} pending`}
                      icon={RotateCcw} colorClass="border-indigo-100 bg-indigo-50 text-indigo-700" />
                    <StatCard label="Marks increased" value={d.revaluation.marks_increased}
                      icon={TrendingUp} colorClass="border-green-100 bg-green-50 text-green-700" />
                    <StatCard label="Unchanged" value={d.revaluation.marks_unchanged}
                      icon={Scale} colorClass="border-gray-100 bg-gray-50 text-gray-700" />
                    <StatCard label="Avg increase"
                      value={d.revaluation.average_increase != null ? `+${d.revaluation.average_increase}` : '—'}
                      sub={d.revaluation.max_increase != null ? `max +${d.revaluation.max_increase}` : undefined}
                      icon={Award} colorClass="border-emerald-100 bg-emerald-50 text-emerald-700" />
                  </div>
                </>
              )}
            </SectionCard>
          )}

          {/* Moderation insights */}
          {has('moderation') && (
            <SectionCard title="Moderation Insights" subtitle="Double-evaluation variance reviews" icon={Scale}>
              {d.moderation.scripts_moderated === 0 ? <EmptyState message="No moderation events" /> : (
                <div className="grid grid-cols-2 gap-3">
                  <StatCard label="Moderated" value={d.moderation.scripts_moderated}
                    sub={`${d.moderation.pending} pending`}
                    icon={Scale} colorClass="border-indigo-100 bg-indigo-50 text-indigo-700" />
                  <StatCard label="Completed" value={d.moderation.completed}
                    icon={CheckCircle2} colorClass="border-green-100 bg-green-50 text-green-700" />
                  <StatCard label="Avg variance"
                    value={d.moderation.average_variance_pct != null ? `${d.moderation.average_variance_pct}%` : '—'}
                    icon={TrendingUp} colorClass="border-amber-100 bg-amber-50 text-amber-700" />
                  <StatCard label="Avg delta"
                    value={d.moderation.average_delta != null ? `${d.moderation.average_delta}` : '—'}
                    sub="moderated − primary"
                    icon={TrendingDown} colorClass="border-teal-100 bg-teal-50 text-teal-700" />
                </div>
              )}
            </SectionCard>
          )}
        </div>
      </div>
    </PageShell>
  )
}
