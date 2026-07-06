import { useNavigate, useParams } from 'react-router-dom'
import { LabReviewForm } from '@/components/labs/LabReviewForm'

export default function LabReviewPanel() {
  const { submissionId } = useParams<{ submissionId: string }>()
  const navigate = useNavigate()
  const sid = submissionId ?? ''

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      <LabReviewForm
        submissionId={sid}
        onBack={(assignmentId) => navigate(`/labs/${assignmentId}`)}
      />
    </div>
  )
}
