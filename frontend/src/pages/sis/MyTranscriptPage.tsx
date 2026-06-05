import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { GraduationCap, Printer, ChevronDown, ChevronUp, Info } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { sisApi, TranscriptSemesterOut, GradeCardSubjectRow } from '@/lib/api/sis'

const RESULT_COLORS: Record<string, string> = {
  PASS:        'bg-green-100 text-green-800 border-green-200',
  FAIL:        'bg-red-100   text-red-800   border-red-200',
  ABSENT:      'bg-orange-100 text-orange-800 border-orange-200',
  WITHHELD:    'bg-purple-100 text-purple-800 border-purple-200',
  PROVISIONAL: 'bg-yellow-100 text-yellow-800 border-yellow-200',
}

function SemesterBlock({ sem }: { sem: TranscriptSemesterOut }) {
  const [open, setOpen] = useState(true)

  return (
    <div className="rounded-md border overflow-hidden mb-4 print:break-inside-avoid">
      <button
        className="w-full flex items-center justify-between px-4 py-3 bg-muted/20 hover:bg-muted/30 text-left"
        onClick={() => setOpen(o => !o)}
      >
        <div className="flex items-center gap-3">
          <div>
            <div className="font-semibold">{sem.snapshot_semester_name}</div>
            <div className="text-xs text-muted-foreground">{sem.snapshot_academic_year}</div>
          </div>
          <Badge variant="outline" className="text-xs">
            {sem.declaration_type}
          </Badge>
        </div>
        <div className="flex items-center gap-4">
          {sem.sgpa !== null && (
            <div className="text-right">
              <div className="font-bold">SGPA: {Number(sem.sgpa).toFixed(2)}</div>
              {sem.cgpa !== null && (
                <div className="text-xs text-muted-foreground">CGPA: {Number(sem.cgpa).toFixed(2)}</div>
              )}
            </div>
          )}
          {sem.overall_result_status && (
            <Badge variant="outline" className={`text-xs ${RESULT_COLORS[sem.overall_result_status] ?? ''}`}>
              {sem.overall_result_status}
            </Badge>
          )}
          {open ? <ChevronUp className="h-4 w-4 text-muted-foreground" /> : <ChevronDown className="h-4 w-4 text-muted-foreground" />}
        </div>
      </button>

      {open && (
        <div className="border-t">
          <table className="w-full text-sm">
            <thead className="bg-muted/20 text-xs uppercase text-muted-foreground">
              <tr>
                <th className="px-4 py-2 text-left">Subject</th>
                <th className="px-4 py-2 text-right">Credits</th>
                <th className="px-4 py-2 text-right">Total</th>
                <th className="px-4 py-2 text-right">%</th>
                <th className="px-4 py-2 text-center">Grade</th>
                <th className="px-4 py-2 text-center">GP</th>
                <th className="px-4 py-2 text-center">Result</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {sem.subjects.map((s: GradeCardSubjectRow, i: number) => (
                <tr key={i} className="hover:bg-muted/10">
                  <td className="px-4 py-2">
                    <div className="font-medium text-xs">{s.course_code || '—'}</div>
                    <div className="text-xs text-muted-foreground">{s.course_name || '—'}</div>
                  </td>
                  <td className="px-4 py-2 text-right text-xs">{s.credits ?? '—'}</td>
                  <td className="px-4 py-2 text-right text-xs">
                    {s.total_marks !== null
                      ? `${Number(s.total_marks).toFixed(1)}/${Number(s.max_marks).toFixed(0)}`
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
            <tfoot className="bg-muted/20 text-xs font-semibold border-t">
              <tr>
                <td className="px-4 py-2" colSpan={2}>
                  Credits: {sem.total_credits_earned ?? '—'} / {sem.total_credits_attempted ?? '—'}
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  )
}

export default function MyTranscriptPage() {
  const { data: transcript, isLoading, isError } = useQuery({
    queryKey: ['my-transcript'],
    queryFn: sisApi.getMyTranscript,
  })

  if (isLoading) return <div className="p-6 text-muted-foreground">Loading your transcript…</div>
  if (isError)   return <div className="p-6 text-red-600">Failed to load transcript. Try again.</div>
  if (!transcript) return null

  return (
    <PageShell>
      <PageHeader
        icon={GraduationCap}
        title="My Academic Transcript"
        subtitle="Complete academic history across all published semesters."
        action={
          <Button size="sm" variant="outline" onClick={() => window.print()}>
            <Printer className="h-4 w-4 mr-1" />Print
          </Button>
        }
      />

      {/* Info */}
      <div className="flex gap-2 items-start rounded-md border border-blue-200 bg-blue-50 p-3 text-sm text-blue-800 mb-4">
        <Info className="h-4 w-4 mt-0.5 shrink-0" />
        Only published and locked results are shown. Draft or unverified results are not visible here.
      </div>

      {/* CGPA summary */}
      {transcript.cgpa !== null && (
        <div className="grid grid-cols-2 gap-3 mb-6">
          <div className="rounded-md border p-4 text-center">
            <div className="text-3xl font-bold">{Number(transcript.cgpa).toFixed(2)}</div>
            <div className="text-sm text-muted-foreground mt-1">Cumulative GPA</div>
          </div>
          <div className="rounded-md border p-4 text-center">
            <div className="text-3xl font-bold">{transcript.total_credits ?? '—'}</div>
            <div className="text-sm text-muted-foreground mt-1">Total Credits Earned</div>
          </div>
        </div>
      )}

      {transcript.semesters.length === 0 ? (
        <div className="text-center py-16 text-muted-foreground">
          No published results yet. Check back after your institution publishes semester results.
        </div>
      ) : (
        <div>
          {transcript.semesters.map((sem: TranscriptSemesterOut) => (
            <SemesterBlock key={sem.declaration_id} sem={sem} />
          ))}
        </div>
      )}
    </PageShell>
  )
}
