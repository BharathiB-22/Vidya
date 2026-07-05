import { History } from 'lucide-react'
import { WidgetCard } from './WidgetCard'

/**
 * No access-tracking instrumentation exists anywhere in the codebase yet
 * (AuditLog only records consequential/AI actions, not passive views — see
 * app/core/audit_log). Rather than fabricate "recently viewed" data, this
 * widget is an honest placeholder until that instrumentation is built.
 */
export function RecentActivity() {
  return (
    <WidgetCard title="Recent Learning Activity" icon={History}>
      <p className="text-sm text-gray-400 py-2">
        Nothing accessed yet. Materials you open will appear here.
      </p>
    </WidgetCard>
  )
}
