import { useNavigate } from 'react-router-dom'
import { ShieldX } from 'lucide-react'
import { Button } from '@/components/ui/button'

export default function UnauthorizedPage() {
  const navigate = useNavigate()

  return (
    <div className="flex flex-col items-center justify-center py-24 text-center px-4">
      <div className="p-4 rounded-full bg-red-50 mb-4">
        <ShieldX className="h-10 w-10 text-red-400" />
      </div>
      <h1 className="text-xl font-bold text-gray-900 mb-2">Access Restricted</h1>
      <p className="text-sm text-gray-500 max-w-sm mb-6">
        You don't have permission to view this page. Contact your administrator if you
        believe this is an error.
      </p>
      <Button variant="outline" onClick={() => navigate('/dashboard')}>
        Go to Dashboard
      </Button>
    </div>
  )
}
