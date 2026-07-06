import { Link } from 'react-router-dom'
import { FlaskConical } from 'lucide-react'

export function LabsTab() {
  return (
    <div className="text-center py-12 rounded-xl border border-dashed border-gray-200">
      <FlaskConical className="h-8 w-8 mx-auto mb-2 text-gray-200" />
      <p className="text-sm text-gray-400 mb-3">
        The full Labs submission workflow is coming to this hub in a future update.
      </p>
      <Link to="/student/labs" className="text-sm text-blue-600 hover:underline">
        Go to My Labs →
      </Link>
    </div>
  )
}
