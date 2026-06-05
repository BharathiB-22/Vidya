import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { BarChart2, ArrowLeft, Trophy } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { sisApi, RankEntryOut } from '@/lib/api/sis'

const RESULT_COLORS: Record<string, string> = {
  PASS:        'bg-green-100 text-green-800 border-green-200',
  FAIL:        'bg-red-100   text-red-800   border-red-200',
  WITHHELD:    'bg-purple-100 text-purple-800 border-purple-200',
  PROVISIONAL: 'bg-yellow-100 text-yellow-800 border-yellow-200',
}

const MEDAL_COLORS: Record<number, string> = {
  1: 'text-yellow-500',
  2: 'text-gray-400',
  3: 'text-amber-600',
}

export default function RankListPage() {
  const { id } = useParams<{ id: string }>()
  const nav = useNavigate()
  const [scope, setScope] = useState<'program' | 'section'>('program')

  const { data: decl } = useQuery({
    queryKey: ['declaration', id],
    queryFn: () => sisApi.getDeclaration(id!),
    enabled: !!id,
  })

  const { data: rankList, isLoading, isError } = useQuery({
    queryKey: ['rank-list', id, scope],
    queryFn: () => sisApi.getRankList(id!, scope),
    enabled: !!id,
  })

  if (isLoading) return <div className="p-6 text-muted-foreground">Loading rank list…</div>
  if (isError)   return <div className="p-6 text-red-600">Failed to load rank list.</div>

  const entries = rankList?.entries ?? []

  return (
    <PageShell>
      <button
        className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-4"
        onClick={() => nav(`/sis/results/${id}`)}
      >
        <ArrowLeft className="h-4 w-4" /> Back to Declaration
      </button>

      <PageHeader
        icon={BarChart2}
        title="Rank List"
        subtitle={decl
          ? `${decl.snapshot_semester_name} · ${decl.snapshot_academic_year} · ${rankList?.total_students ?? 0} students`
          : `${rankList?.total_students ?? 0} students`}
        action={
          <div className="flex gap-1">
            <Button size="sm" variant={scope === 'program' ? 'default' : 'outline'}
              onClick={() => setScope('program')}>Program</Button>
            <Button size="sm" variant={scope === 'section' ? 'default' : 'outline'}
              onClick={() => setScope('section')}>Section</Button>
          </div>
        }
      />

      {entries.length === 0 ? (
        <div className="text-center py-16 text-muted-foreground">
          No rankings available. Compute results and ranks first.
        </div>
      ) : (
        <div className="rounded-md border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted/20 text-xs uppercase text-muted-foreground">
              <tr>
                <th className="px-4 py-2 text-center w-16">Rank</th>
                <th className="px-4 py-2 text-left">Student</th>
                <th className="px-4 py-2 text-right">SGPA</th>
                <th className="px-4 py-2 text-right">CGPA</th>
                <th className="px-4 py-2 text-right">Credits</th>
                <th className="px-4 py-2 text-center">Result</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {entries.map((e: RankEntryOut) => (
                <tr key={e.student_id}
                  className={`hover:bg-muted/10 ${e.rank <= 3 ? 'bg-amber-50/40' : ''}`}>
                  <td className="px-4 py-2 text-center">
                    <span className={`font-bold text-lg ${MEDAL_COLORS[e.rank] ?? 'text-muted-foreground'}`}>
                      {e.rank <= 3 ? <Trophy className="h-4 w-4 inline mr-0.5" /> : null}
                      #{e.rank}
                    </span>
                  </td>
                  <td className="px-4 py-2">
                    <span className="font-mono text-xs">{e.student_id.slice(0, 8)}…</span>
                  </td>
                  <td className="px-4 py-2 text-right font-semibold">
                    {e.sgpa !== null ? Number(e.sgpa).toFixed(2) : '—'}
                  </td>
                  <td className="px-4 py-2 text-right text-muted-foreground">
                    {e.cgpa !== null ? Number(e.cgpa).toFixed(2) : '—'}
                  </td>
                  <td className="px-4 py-2 text-right text-xs text-muted-foreground">
                    {e.total_credits_earned ?? '—'}
                  </td>
                  <td className="px-4 py-2 text-center">
                    {e.overall_result_status ? (
                      <Badge variant="outline" className={`text-xs ${RESULT_COLORS[e.overall_result_status] ?? ''}`}>
                        {e.overall_result_status}
                      </Badge>
                    ) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </PageShell>
  )
}
