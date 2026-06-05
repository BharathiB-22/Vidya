import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Award, ArrowLeft, Printer } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { sisApi, GradeCardOut, GradeCardSubjectRow } from '@/lib/api/sis'

const RESULT_COLORS: Record<string, string> = {
  PASS:        'bg-green-100 text-green-800 border-green-200',
  FAIL:        'bg-red-100   text-red-800   border-red-200',
  ABSENT:      'bg-orange-100 text-orange-800 border-orange-200',
  WITHHELD:    'bg-purple-100 text-purple-800 border-purple-200',
  PROVISIONAL: 'bg-yellow-100 text-yellow-800 border-yellow-200',
}

function GradeCardRow({ card }: { card: GradeCardOut }) {
  return (
    <div className="rounded-md border overflow-hidden mb-4 print:break-inside-avoid">
      {/* Header */}
      <div className="bg-muted/20 px-4 py-3 flex items-center justify-between">
        <div>
          <div className="font-semibold text-sm">Student: {card.student_id.slice(0, 8)}…</div>
          <div className="text-xs text-muted-foreground">
            {card.snapshot_semester_name} · {card.snapshot_academic_year}
          </div>
        </div>
        <div className="text-right">
          {card.sgpa !== null && (
            <div className="text-lg font-bold">SGPA: {Number(card.sgpa).toFixed(2)}</div>
          )}
          {card.cgpa !== null && (
            <div className="text-xs text-muted-foreground">CGPA: {Number(card.cgpa).toFixed(2)}</div>
          )}
          {card.overall_result_status && (
            <Badge variant="outline" className={`text-xs mt-1 ${RESULT_COLORS[card.overall_result_status] ?? ''}`}>
              {card.overall_result_status}
            </Badge>
          )}
        </div>
      </div>

      {/* Subjects table */}
      <table className="w-full text-sm">
        <thead className="bg-muted/20 text-xs uppercase text-muted-foreground">
          <tr>
            <th className="px-4 py-2 text-left">Subject</th>
            <th className="px-4 py-2 text-right">Credits</th>
            <th className="px-4 py-2 text-right">Int</th>
            <th className="px-4 py-2 text-right">Ext</th>
            <th className="px-4 py-2 text-right">Grace</th>
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
              <td className="px-4 py-2 text-right text-xs">{s.internal_marks !== null ? Number(s.internal_marks).toFixed(1) : '—'}</td>
              <td className="px-4 py-2 text-right text-xs">{s.external_marks !== null ? Number(s.external_marks).toFixed(1) : '—'}</td>
              <td className="px-4 py-2 text-right text-xs text-amber-600">
                {s.grace_marks ? `+${Number(s.grace_marks).toFixed(1)}` : '—'}
              </td>
              <td className="px-4 py-2 text-right font-medium text-xs">
                {s.total_marks !== null ? `${Number(s.total_marks).toFixed(1)}/${Number(s.max_marks).toFixed(0)}` : '—'}
              </td>
              <td className="px-4 py-2 text-right text-xs">
                {s.percentage !== null ? `${Number(s.percentage).toFixed(1)}%` : '—'}
              </td>
              <td className="px-4 py-2 text-center">
                <span className="font-bold text-sm">{s.grade_letter ?? '—'}</span>
              </td>
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
        <tfoot className="bg-muted/20 text-xs font-semibold border-t">
          <tr>
            <td className="px-4 py-2" colSpan={2}>
              Credits: {card.total_credits_earned ?? '—'} / {card.total_credits_attempted ?? '—'}
            </td>
            {card.section_rank && (
              <td className="px-4 py-2 text-right" colSpan={4}>
                Section Rank: #{card.section_rank}
              </td>
            )}
            {card.program_rank && (
              <td className="px-4 py-2 text-right" colSpan={4}>
                Program Rank: #{card.program_rank}
              </td>
            )}
          </tr>
        </tfoot>
      </table>
    </div>
  )
}

export default function GradeCardPage() {
  const { id } = useParams<{ id: string }>()
  const nav = useNavigate()

  const { data: decl } = useQuery({
    queryKey: ['declaration', id],
    queryFn: () => sisApi.getDeclaration(id!),
    enabled: !!id,
  })

  const { data: cards, isLoading, isError } = useQuery({
    queryKey: ['grade-cards', id],
    queryFn: () => sisApi.listGradeCards(id!),
    enabled: !!id,
  })

  if (isLoading) return <div className="p-6 text-muted-foreground">Loading grade cards…</div>
  if (isError)   return <div className="p-6 text-red-600">Failed to load grade cards.</div>

  const cardList = cards ?? []

  return (
    <PageShell>
      <button
        className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-4"
        onClick={() => nav(`/sis/results/${id}`)}
      >
        <ArrowLeft className="h-4 w-4" /> Back to Declaration
      </button>

      <PageHeader
        icon={Award}
        title="Grade Cards"
        subtitle={decl
          ? `${decl.snapshot_semester_name} · ${decl.snapshot_academic_year} · ${cardList.length} students`
          : `${cardList.length} students`}
        action={
          <Button size="sm" variant="outline" onClick={() => window.print()}>
            <Printer className="h-4 w-4 mr-1" />Print All
          </Button>
        }
      />

      {cardList.length === 0 ? (
        <div className="text-center py-16 text-muted-foreground">
          No grade cards yet. Compute results first.
        </div>
      ) : (
        <div>
          {cardList.map((card: GradeCardOut) => (
            <GradeCardRow key={card.student_id} card={card} />
          ))}
        </div>
      )}
    </PageShell>
  )
}
