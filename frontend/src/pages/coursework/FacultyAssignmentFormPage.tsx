import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ChevronLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { AssignmentForm } from '@/components/coursework/AssignmentForm'

export default function FacultyAssignmentFormPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const syllabusIdFromQuery = searchParams.get('syllabus_id') ?? undefined

  return (
    <div className="max-w-2xl mx-auto px-4 py-8 space-y-6">
      <Button variant="ghost" size="sm" className="-ml-1" onClick={() => navigate('/faculty/assignments')}>
        <ChevronLeft className="h-4 w-4 mr-1" />
        All Assignments
      </Button>

      <AssignmentForm
        assignmentId={id}
        syllabusId={syllabusIdFromQuery}
        onCreated={(created) => navigate(`/faculty/assignments/${created.id}/submissions`)}
        onUpdated={() => navigate('/faculty/assignments')}
      />
    </div>
  )
}
