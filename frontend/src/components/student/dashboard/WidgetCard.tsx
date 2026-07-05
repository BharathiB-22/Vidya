import { Link } from 'react-router-dom'
import { AlertCircle, ChevronRight } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

interface WidgetCardProps {
  title: string
  icon: LucideIcon
  isLoading?: boolean
  isError?: boolean
  errorMessage?: string
  action?: { label: string; to: string }
  children: React.ReactNode
}

function SkeletonBody() {
  return (
    <div className="space-y-2.5 animate-pulse" aria-hidden="true">
      <div className="h-3.5 w-3/4 rounded bg-gray-100" />
      <div className="h-3.5 w-1/2 rounded bg-gray-100" />
      <div className="h-3.5 w-2/3 rounded bg-gray-100" />
    </div>
  )
}

export function WidgetCard({ title, icon: Icon, isLoading, isError, errorMessage, action, children }: WidgetCardProps) {
  return (
    <section className="rounded-xl border border-gray-200 bg-white p-5 flex flex-col gap-3.5" aria-labelledby={`widget-${title}`}>
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Icon className="h-4 w-4 text-sv-primary" aria-hidden="true" />
          <h3 id={`widget-${title}`} className="text-sm font-bold text-gray-900">{title}</h3>
        </div>
        {action && (
          <Link
            to={action.to}
            className="text-xs font-semibold text-sv-primary hover:underline inline-flex items-center gap-0.5 flex-shrink-0"
          >
            {action.label}
            <ChevronRight className="h-3 w-3" />
          </Link>
        )}
      </div>

      {isLoading ? (
        <SkeletonBody />
      ) : isError ? (
        <div className="flex items-start gap-2 text-xs text-red-500 py-1" role="alert">
          <AlertCircle className="h-3.5 w-3.5 flex-shrink-0 mt-0.5" />
          <span>{errorMessage ?? 'Could not load this widget.'}</span>
        </div>
      ) : (
        children
      )}
    </section>
  )
}
