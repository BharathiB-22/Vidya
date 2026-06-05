import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Award, Printer, Lock, Info } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { sisApi, GradeCardSubjectRow } from '@/lib/api/sis'

const RESULT_COLORS: Record<string, string> = {
  PASS:        'bg-green-100 text-green-800 border-green-200',
  FAIL:        'bg-red-100   text-red-800   border-red-200',
  ABSENT:      'bg-orange-100 text-orange-800 border-orange-200',
  WITHHELD:    'bg-purple-100 text-purple-800 border-purple-200',
  PROVISIONAL: 'bg-yellow-100 text-yellow-800 border-yellow-200',
}

export default function MyGradeCardPage() {
  const { declId } = useParams<{ declId: string }>()

  const { data: card, isLoading, isError, error } = useQuery({
    queryKey: ['my-grade-card', declId],
    queryFn: () => sisApi.getMyGradeCard(declId!),
    enabled: !!declId,
    retry: false,
  })

  if (isLoading) return <div className="p-6 text-muted-foreground">Loading your grade card…</div>
  if (isError) {
    const msg = String(error)
    const isNotPublished = msg.includes('403') || msg.toLowerCase().includes('not yet published')
    return (
      <div className="p-6">
        <div className="flex gap-2 items-start rounded-md border border-yellow-200 bg-yellow-50 p-4 text-sm text-yellow-800">
          <Lock className="h-4 w-4 mt-0.5 shrink-0" />
          {isNotPublished
            ? 'This result has not been published yet. Check back after your institution publishes the results.'
            : 'Failed to load grade card. Please try again.'}
        </div>
      </div>
    )
  }
  if (!card) return null

  return (
    <PageShell>
      <PageHeader
        icon={Award}
        title="My Grade Card"
        subtitle={`${card.snapshot_semester_name} · ${card.snapshot_academic_year}`}
        action={
          <Button size="sm" variant="outline" onClick={() => window.print()}>
            <Printer className="h-4 w-4 mr-1" />Print
          </Button>
        }
      />

      {/* Info banner */}
      <div className="flex gap-2 items-start rounded-md border border-blue-200 bg-blue-50 p-3 text-sm text-blue-800 mb-4">
        <Info className="h-4 w-4 mt-0.5 shrink-0" />
        This is your official grade card. Grading policy: {card.snapshot_grading_policy_name}.
        {card.published_at && ` Published on ${new Date(card.published_at).toLocaleDateString()}.`}
      </div>

      {/* Summary row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        {[
          { label: 'SGPA', value: card.sgpa !== null ? Number(card.sgpa).toFixed(2) : '—' },
          { label: 'CGPA', value: card.cgpa !== null ? Number(card.cgpa).toFixed(2) : '—' },
          { label: 'Credits Earned', value: card.total_credits_earned ?? '—' },
          { label: 'Section Rank', value: card.section_rank ? `#${card.section_rank}` : '—' },
        ].map(({ label, value }) => (
          <div key={label} className="rounded-md border p-3 text-center">
            <div className="text-2xl font-bold">{String(value)}</div>
            <div className="text-xs text-muted-foreground mt-1">{label}</div>
          </div>
        ))}
      </div>

      {/* Overall result */}
      {card.overall_result_status && (
        <div className={`flex items-center justify-center gap-2 rounded-md border p-3 mb-6 font-semibold ${
          RESULT_COLORS[card.overall_result_status] ?? 'bg-muted/20'
        }`}>
          Overall Result: {card.overall_result_status}
        </div>
      )}

      {/* Subjects table */}
      <div className="rounded-md border overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-muted/20 text-xs uppercase text-muted-foreground">
            <tr>
              <th className="px-4 py-2 text-left">Subject</th>
              <th className="px-4 py-2 text-right">Credits</th>
              <th className="px-4 py-2 text-right">Internal</th>
              <th className="px-4 py-2 text-right">External</th>
              <th className="px-4 py-2 text-right">Total</th>
              <th className="px-4 py-2 text-right">%</th>
              <th className="px-4 py-2 text-center">Grade</th>
              <th className="px-4 py-2 text-center">GP</th>
              <th className="px-4 py-2 text-center">Result</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {card.subjects.map((s: GradeCardSubjectRow, i: number) => (
              <tr key={i} className="hover:bg-muted/10">
                <td className="px-4 py-2">
                  <div className="font-medium text-xs">{s.course_code || '—'}</div>
                  <div className="text-xs text-muted-foreground">{s.course_name || '—'}</div>
                </td>
                <td className="px-4 py-2 text-right text-xs">{s.credits ?? '—'}</td>
                <td className="px-4 py-2 text-right text-xs">
                  {s.internal_marks !== null ? Number(s.internal_marks).toFixed(1) : '—'}
                </td>
                <td className="px-4 py-2 text-right text-xs">
                  {s.external_marks !== null ? Number(s.external_marks).toFixed(1) : '—'}
                </td>
                <td className="px-4 py-2 text-right font-medium text-xs">
                  {s.total_marks !== null
                    ? `${Number(s.total_marks).toFixed(1)} / ${Number(s.max_marks).toFixed(0)}`
                    : '—'}
                </td>
                <td className="px-4 py-2 text-right text-xs">
                  {s.percentage !== null ? `${Number(s.percentage).toFixed(1)}%` : '—'}
                </td>
                <td className="px-4 py-2 text-center font-bold">{s.grade_letter ?? '—'}</td>
                <td className="px-4 py-2 text-center text-xs">
                  {s.grade_point !== null ? Number(s.grade_point).toFixed(1) : '—'}
                </td>
                <td className="px-4 py-2 text-center">
                  <Badge variant="outline" className={`text-xs ${RESULT_COLORS[s.result_status] ?? ''}`}>
                    {s.result_status}
                  </Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </PageShell>
  )
}
