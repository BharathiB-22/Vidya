import type { LucideIcon } from 'lucide-react'

interface PageHeaderProps {
  icon: LucideIcon
  title: string
  subtitle?: string
  action?: React.ReactNode
}

export function PageHeader({ icon: Icon, title, subtitle, action }: PageHeaderProps) {
  return (
    <div className="flex items-center justify-between gap-4 flex-wrap">
      <div className="flex items-center gap-3">
        <div className="p-2 rounded-lg bg-gray-100 border border-gray-200 flex-shrink-0">
          <Icon className="h-5 w-5 text-gray-600" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-gray-900 leading-tight">{title}</h1>
          {subtitle && <p className="text-sm text-gray-500 mt-0.5">{subtitle}</p>}
        </div>
      </div>
      {action && <div className="flex-shrink-0">{action}</div>}
    </div>
  )
}
