// M07 Research Supervision — Guide/Admin: Research problem detail page
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ResearchProblemPanel } from '@/components/research/ResearchProblemPanel'

export default function ResearchProblemDetailPage() {
  const { problemId } = useParams<{ problemId: string }>()
  const navigate = useNavigate()

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">
      <Button variant="ghost" size="sm" className="-ml-1" onClick={() => navigate('/research/problems')}>
        <ArrowLeft className="h-4 w-4 mr-1" />
        Research Proposals
      </Button>

      <ResearchProblemPanel problemId={problemId ?? ''} />
    </div>
  )
}
