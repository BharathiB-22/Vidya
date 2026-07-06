import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Microscope, ExternalLink, Users, Clock, Video } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { listProblems, listVivasForGuide } from '@/lib/api/research'
import { useCurrentUser } from '@/hooks/useCurrentUser'
import { ResearchProblemPanel } from '@/components/research/ResearchProblemPanel'

const VIVA_VARIANT: Record<string, 'default' | 'success' | 'info' | 'warning'> = {
  SCHEDULED: 'default',
  IN_PROGRESS: 'warning',
  ASR_PROCESSING: 'warning',
  COMPLETED: 'info',
  EVALUATED: 'info',
  GUIDE_RATIFIED: 'success',
}

export function ResearchTab() {
  const navigate = useNavigate()
  const user = useCurrentUser()
  const isGuide = user?.responsibilities?.includes('GUIDE') ?? false
  const [openProblemId, setOpenProblemId] = useState<string | null>(null)

  const acceptedQ = useQuery({
    queryKey: ['guide-problems', 'ACCEPTED'],
    queryFn: () => listProblems({ status: 'ACCEPTED' }),
    enabled: isGuide,
  })
  const pendingQ = useQuery({
    queryKey: ['guide-problems', 'PENDING_REVIEW'],
    queryFn: () => listProblems({ status: 'PENDING_REVIEW' }),
    enabled: isGuide,
  })
  const vivasQ = useQuery({
    queryKey: ['guide-vivas'],
    queryFn: () => listVivasForGuide(),
    enabled: isGuide,
  })

  if (!isGuide) {
    return (
      <div className="text-center py-12 rounded-xl border border-dashed border-gray-200">
        <Microscope className="h-8 w-8 mx-auto mb-2 text-gray-200" />
        <p className="text-sm text-gray-400">You do not hold the Research Guide responsibility.</p>
      </div>
    )
  }

  const recentVivas = [...(vivasQ.data?.items ?? [])]
    .sort((a, b) => (b.completed_at ?? b.scheduled_at).localeCompare(a.completed_at ?? a.scheduled_at))
    .slice(0, 5)

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <Users className="h-4 w-4 text-gray-400 mb-2" />
          <p className="text-xl font-bold text-gray-900">{acceptedQ.isLoading ? '…' : (acceptedQ.data?.total ?? 0)}</p>
          <p className="text-xs text-gray-500 mt-0.5">Problems Under Your Supervision</p>
        </div>
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <Clock className="h-4 w-4 text-amber-500 mb-2" />
          <p className="text-xl font-bold text-gray-900">{pendingQ.isLoading ? '…' : (pendingQ.data?.total ?? 0)}</p>
          <p className="text-xs text-gray-500 mt-0.5">Pending Your Evaluation</p>
        </div>
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <Video className="h-4 w-4 text-gray-400 mb-2" />
          <p className="text-xl font-bold text-gray-900">{vivasQ.isLoading ? '…' : (vivasQ.data?.total ?? 0)}</p>
          <p className="text-xs text-gray-500 mt-0.5">Viva Sessions</p>
        </div>
      </div>

      {(pendingQ.data?.items.length ?? 0) > 0 && (
        <div>
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">Pending Evaluations</p>
          <div className="rounded-xl border border-amber-200 divide-y divide-amber-100 bg-amber-50/40 overflow-hidden">
            {pendingQ.data!.items.slice(0, 5).map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => setOpenProblemId(p.id)}
                className="w-full text-left px-4 py-3 hover:bg-amber-50 transition-colors"
              >
                <p className="text-sm font-medium text-gray-800 truncate">{p.title}</p>
              </button>
            ))}
          </div>
        </div>
      )}

      {(acceptedQ.data?.items.length ?? 0) > 0 && (
        <div>
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">Current Supervision</p>
          <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
            {acceptedQ.data!.items.slice(0, 5).map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => setOpenProblemId(p.id)}
                className="w-full text-left px-4 py-3 hover:bg-gray-50 transition-colors"
              >
                <p className="text-sm font-medium text-gray-800 truncate">{p.title}</p>
              </button>
            ))}
          </div>
        </div>
      )}

      <div>
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">Recent Viva</p>
        {vivasQ.isLoading ? (
          <div className="text-sm text-gray-400 py-6 text-center">Loading viva sessions…</div>
        ) : recentVivas.length === 0 ? (
          <div className="text-center py-8 rounded-xl border border-dashed border-gray-200">
            <Video className="h-6 w-6 mx-auto mb-2 text-gray-200" />
            <p className="text-sm text-gray-400">No viva sessions yet.</p>
          </div>
        ) : (
          <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
            {recentVivas.map((v) => (
              <button
                key={v.id}
                type="button"
                onClick={() => navigate(`/research/vivas/${v.id}`)}
                className="w-full text-left flex items-center justify-between gap-3 px-4 py-3 hover:bg-gray-50 transition-colors"
              >
                <p className="text-sm text-gray-600">
                  {new Date(v.completed_at ?? v.scheduled_at).toLocaleDateString()}
                </p>
                <Badge variant={VIVA_VARIANT[v.status] ?? 'default'}>{v.status}</Badge>
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="flex justify-end">
        <Button size="sm" onClick={() => navigate('/research/problems')}>
          <ExternalLink className="h-3.5 w-3.5 mr-1.5" />
          Open Research Supervision
        </Button>
      </div>
      <p className="text-xs text-gray-400">
        Research supervision is not yet tracked per-subject — figures above cover all students you guide.
      </p>

      <Dialog open={!!openProblemId} onOpenChange={(open) => !open && setOpenProblemId(null)}>
        <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
          {openProblemId && <ResearchProblemPanel problemId={openProblemId} />}
        </DialogContent>
      </Dialog>
    </div>
  )
}
