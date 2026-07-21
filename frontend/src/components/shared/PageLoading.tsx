import { Loader2 } from 'lucide-react'

export function PageLoading({ message = 'Loading…' }: { message?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-16 text-gray-600 text-sm">
      <Loader2 className="w-5 h-5 animate-spin" />
      {message}
    </div>
  )
}
