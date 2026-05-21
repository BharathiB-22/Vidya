import { AlertTriangle, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface PageErrorProps {
  message?: string
  onRetry?: () => void
}

export function PageError({
  message = 'Something went wrong. Please try again.',
  onRetry,
}: PageErrorProps) {
  return (
    <div className="rounded-lg bg-red-50 border border-red-200 p-4 flex items-start gap-3">
      <AlertTriangle className="w-4 h-4 text-red-500 flex-shrink-0 mt-0.5" />
      <p className="text-sm text-red-700 flex-1">{message}</p>
      {onRetry && (
        <Button
          variant="ghost"
          size="sm"
          onClick={onRetry}
          className="text-red-600 hover:text-red-700 hover:bg-red-100 h-7 px-2 shrink-0 gap-1"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          Retry
        </Button>
      )}
    </div>
  )
}
