import { useNavigate, useParams } from 'react-router-dom'
import { ChevronLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { AssignmentGradingPanel } from '@/components/coursework/AssignmentGradingPanel'

export default function FacultyAssignmentGradingPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const assignmentId = id ?? ''

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">
      <Button variant="ghost" size="sm" className="-ml-1" onClick={() => navigate('/faculty/assignments')}>
        <ChevronLeft className="h-4 w-4 mr-1" />
        All Assignments
      </Button>

      <AssignmentGradingPanel assignmentId={assignmentId} />
    </div>
  )
}
