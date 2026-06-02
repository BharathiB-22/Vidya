import type { LucideIcon } from 'lucide-react'
import { Inbox } from 'lucide-react'

interface PageEmptyProps {
  icon?: LucideIcon
  title?: string
  message?: string
  description?: string
  action?: React.ReactNode
}

export function PageEmpty({
  icon: Icon = Inbox,
  title,
  message = 'Nothing here yet.',
  description,
  action,
}: PageEmptyProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center gap-3 max-w-sm mx-auto">
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gray-50 border border-gray-100">
        <Icon className="w-7 h-7 text-gray-300" />
      </div>
      <div className="space-y-1">
        {title && (
          <p className="text-sm font-semibold text-gray-700">{title}</p>
        )}
        <p className="text-sm text-gray-400">{message}</p>
        {description && (
          <p className="text-xs text-gray-400 leading-relaxed">{description}</p>
        )}
      </div>
      {action && <div className="mt-1">{action}</div>}
    </div>
  )
}
