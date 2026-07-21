import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Users, Crown, Building2, Mail, Shield } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { PageLoading } from '@/components/shared/PageLoading'
import { sisApi } from '@/lib/api/sis'
import type { GovernanceDeanItem, GovernanceBoardItem } from '@/lib/api/sis'

// Responsibility-chip colors
const RESP_COLORS: Record<string, string> = {
  GUIDE: '#6366f1',
  EVALUATOR: '#10b981',
  DEAN: '#ec4899',
}

function RespChip({ label }: { label: string }) {
  const bg = RESP_COLORS[label] ?? '#6b7280'
  return (
    <span
      className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium"
      style={{ background: `${bg}20`, color: bg, border: `1px solid ${bg}40` }}
    >
      {label}
    </span>
  )
}

function StatusDot({ isActive }: { isActive: boolean }) {
  return (
    <span
      className="inline-block w-2 h-2 rounded-full flex-shrink-0"
      style={{ background: isActive ? '#10b981' : '#6b7280' }}
      title={isActive ? 'Active' : 'Inactive'}
    />
  )
}

// ---------------------------------------------------------------------------
// Deans tab
// ---------------------------------------------------------------------------

function DeansTab() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['governance-deans'],
    queryFn: sisApi.listGovernanceDeans,
  })

  if (isLoading) return <PageLoading />
  if (error) return (
    <div className="text-center py-16 text-red-400 text-sm">
      Failed to load deans. Please refresh.
    </div>
  )

  const items = data?.items ?? []

  if (items.length === 0) {
    return (
      <div className="text-center py-16 text-slate-700 text-sm">
        No deans found.
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {items.map((dean: GovernanceDeanItem) => (
        <DeanCard key={dean.user_id} dean={dean} />
      ))}
    </div>
  )
}

function DeanCard({ dean }: { dean: GovernanceDeanItem }) {
  return (
    <div
      className="rounded-xl p-4 flex items-start gap-4"
      style={{ background: '#ffffff', border: '1px solid #E5E7EB' }}
    >
      <div
        className="w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 text-sm font-bold"
        style={{ background: '#ec489920', color: '#ec4899', border: '1px solid #ec489940' }}
      >
        {dean.full_name.charAt(0).toUpperCase()}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <StatusDot isActive={dean.is_active} />
          <span className="font-semibold text-slate-900 text-sm">{dean.full_name}</span>
          {dean.designation && (
            <span className="text-xs text-slate-700">{dean.designation}</span>
          )}
        </div>
        <div className="flex items-center gap-1 mt-1 text-xs text-slate-700">
          <Mail size={12} />
          <span>{dean.email}</span>
        </div>
        {dean.department && (
          <div className="flex items-center gap-1 mt-0.5 text-xs text-slate-700">
            <Building2 size={12} />
            <span>{dean.department.name}</span>
            <span className="text-slate-800">({dean.department.code})</span>
          </div>
        )}
        {dean.responsibilities.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-2">
            {dean.responsibilities.map(r => <RespChip key={r} label={r} />)}
          </div>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Board tab
// ---------------------------------------------------------------------------

function BoardTab() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['governance-board'],
    queryFn: sisApi.listGovernanceBoard,
  })

  if (isLoading) return <PageLoading />
  if (error) return (
    <div className="text-center py-16 text-red-400 text-sm">
      Failed to load board members. Please refresh.
    </div>
  )

  const items = data?.items ?? []

  if (items.length === 0) {
    return (
      <div className="text-center py-16 text-slate-700 text-sm">
        No board members found.
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {items.map((member: GovernanceBoardItem) => (
        <BoardCard key={member.user_id} member={member} />
      ))}
    </div>
  )
}

function BoardCard({ member }: { member: GovernanceBoardItem }) {
  return (
    <div
      className="rounded-xl p-4 flex items-start gap-4"
      style={{ background: '#ffffff', border: '1px solid #E5E7EB' }}
    >
      <div
        className="w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 text-sm font-bold"
        style={{ background: '#f59e0b20', color: '#f59e0b', border: '1px solid #f59e0b40' }}
      >
        {member.full_name.charAt(0).toUpperCase()}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <StatusDot isActive={member.is_active} />
          <span className="font-semibold text-slate-900 text-sm">{member.full_name}</span>
          {member.designation && (
            <span className="text-xs text-slate-700">{member.designation}</span>
          )}
        </div>
        <div className="flex items-center gap-1 mt-1 text-xs text-slate-700">
          <Mail size={12} />
          <span>{member.email}</span>
        </div>
        {member.department && (
          <div className="flex items-center gap-1 mt-0.5 text-xs text-slate-700">
            <Building2 size={12} />
            <span>{member.department.name}</span>
            <span className="text-slate-800">({member.department.code})</span>
          </div>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

type Tab = 'deans' | 'board'

export default function GovernanceDirectoryPage() {
  const [activeTab, setActiveTab] = useState<Tab>('deans')

  return (
    <PageShell>
      <PageHeader
        title="Governance Directory"
        subtitle="Academic leadership and examination governance — read-only"
        icon={Shield}
      />

      {/* Tab bar */}
      <div className="flex gap-1 mb-6 border-b border-slate-200 pb-0">
        <TabButton
          active={activeTab === 'deans'}
          onClick={() => setActiveTab('deans')}
          icon={Crown}
          label="Deans"
        />
        <TabButton
          active={activeTab === 'board'}
          onClick={() => setActiveTab('board')}
          icon={Users}
          label="Board Members"
        />
      </div>

      {activeTab === 'deans' && <DeansTab />}
      {activeTab === 'board' && <BoardTab />}
    </PageShell>
  )
}

function TabButton({
  active,
  onClick,
  icon: Icon,
  label,
}: {
  active: boolean
  onClick: () => void
  icon: LucideIcon
  label: string
}) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px"
      style={{
        borderColor: active ? '#7c3aed' : 'transparent',
        color: active ? '#7c3aed' : '#6b7280',
      }}
    >
      <Icon size={14} />
      {label}
    </button>
  )
}
