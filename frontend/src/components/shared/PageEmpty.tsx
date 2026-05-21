import type { LucideIcon } from 'lucide-react'
import { Inbox } from 'lucide-react'

interface PageEmptyProps {
  icon?: LucideIcon
  message?: string
  action?: React.ReactNode
}

export function PageEmpty({
  icon: Icon = Inbox,
  message = 'Nothing here yet.',
  action,
}: PageEmptyProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-gray-400 gap-3">
      <Icon className="w-10 h-10 text-gray-200" />
      <p className="text-sm">{message}</p>
      {action && <div>{action}</div>}
    </div>
  )
}
