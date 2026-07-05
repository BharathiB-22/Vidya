import { ChevronRight } from 'lucide-react'

export type IconComponent = React.FC<{ className?: string }>

export interface ModuleCard {
  title: string
  description: string
  to: string
  icon: IconComponent
  roles: string[]
  badge: string
  bar: string
  section: string
}

export interface AdminCard {
  title: string
  description: string
  to?: string
  icon: IconComponent
  bar: string
  badge: string
}

interface StatCardProps {
  label: string
  value: string
  icon: IconComponent
  accent?: boolean
}

export function StatCard({ label, value, icon: Icon, accent }: StatCardProps) {
  return (
    <div className={`rounded-xl border px-4 py-3.5 flex items-start gap-3 ${
      accent
        ? 'bg-sv-light border-sv-primary/20'
        : 'bg-white border-gray-200'
    }`}>
      <div className={`p-1.5 rounded-lg mt-0.5 ${accent ? 'bg-sv-primary/10' : 'bg-gray-100'}`}>
        <Icon className={`h-3.5 w-3.5 ${accent ? 'text-sv-primary' : 'text-gray-400'}`} />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wide">{label}</p>
        <p className={`text-sm font-bold mt-0.5 truncate ${accent ? 'text-sv-primary' : 'text-gray-900'}`}>
          {value}
        </p>
      </div>
    </div>
  )
}

export function ModuleCardItem({ card, onClick }: { card: ModuleCard; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="text-left w-full rounded-xl border border-gray-200 bg-white hover:border-sv-primary/30 hover:shadow-lg hover:shadow-sv-primary/5 transition-all duration-200 group relative overflow-hidden"
    >
      <div className={`absolute inset-x-0 top-0 h-[3px] ${card.bar}`} />
      <div className="p-5 pt-6">
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className={`p-2 rounded-lg border ${card.badge}`}>
            <card.icon className="h-4 w-4" />
          </div>
          <ChevronRight className="h-4 w-4 text-gray-300 group-hover:text-sv-primary mt-0.5 transition-colors duration-200" />
        </div>
        <p className="text-sm font-semibold text-gray-900 leading-snug">{card.title}</p>
        <p className="text-xs text-gray-500 mt-1 leading-relaxed">{card.description}</p>
      </div>
    </button>
  )
}

export function AdminActionCard({ card, onClick }: { card: AdminCard; onClick?: () => void }) {
  const soon = !card.to
  return (
    <button
      onClick={soon ? undefined : onClick}
      disabled={soon}
      className={`text-left w-full rounded-xl border border-gray-200 bg-white transition-all duration-200 group relative overflow-hidden disabled:opacity-40 disabled:cursor-not-allowed ${
        soon ? '' : 'hover:border-sv-primary/30 hover:shadow-lg hover:shadow-sv-primary/5'
      }`}
    >
      <div className={`absolute inset-x-0 top-0 h-[3px] ${card.bar}`} />
      <div className="p-5 pt-6">
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className={`p-2 rounded-lg border ${card.badge}`}>
            <card.icon className="h-4 w-4" />
          </div>
          {soon ? (
            <span className="text-[9px] px-1.5 py-0.5 rounded font-bold uppercase bg-gray-100 text-gray-400 border border-gray-200 self-start mt-0.5 flex-shrink-0">
              Soon
            </span>
          ) : (
            <ChevronRight className="h-4 w-4 text-gray-300 group-hover:text-sv-primary mt-0.5 transition-colors duration-200 flex-shrink-0" />
          )}
        </div>
        <p className="text-sm font-semibold text-gray-900 leading-snug">{card.title}</p>
        <p className="text-xs text-gray-500 mt-1 leading-relaxed">{card.description}</p>
      </div>
    </button>
  )
}

export function getGreeting(): string {
  const hour = new Date().getHours()
  if (hour < 12) return 'Good morning'
  if (hour < 17) return 'Good afternoon'
  return 'Good evening'
}

const HONORIFICS = new Set(['dr.', 'prof.', 'mr.', 'ms.', 'mrs.', 'mx.', 'sir'])

export function getDisplayFirstName(fullName: string): string {
  const parts = fullName.trim().split(/\s+/).filter(Boolean)
  if (parts.length <= 1) return parts[0] ?? ''
  if (HONORIFICS.has(parts[0].toLowerCase())) return `${parts[0]} ${parts[1]}`
  return parts[0]
}
