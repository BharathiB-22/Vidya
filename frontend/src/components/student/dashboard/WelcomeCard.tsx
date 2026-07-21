import { GraduationCap, Building2, Users, BookOpen } from 'lucide-react'
import { useActiveSemester } from '@/hooks/useActiveSemester'
import { getGreeting, getDisplayFirstName } from '@/components/dashboard/shared'

function InfoChip({ icon: Icon, label, value }: { icon: React.FC<{ className?: string }>; label: string; value: string }) {
  return (
    <div className="flex items-center gap-1.5 text-xs text-gray-500">
      <Icon className="h-3.5 w-3.5 text-gray-600 flex-shrink-0" />
      <span className="text-gray-600">{label}:</span>
      <span className="font-semibold text-gray-700 truncate">{value}</span>
    </div>
  )
}

export function WelcomeCard() {
  const { profile, activeSemester, isProfileLoading: isLoading } = useActiveSemester()

  const firstName = profile?.full_name ? getDisplayFirstName(profile.full_name) : null

  return (
    <section className="rounded-xl border border-gray-200 bg-white p-5 flex items-center gap-4">
      <div className="h-16 w-16 rounded-full bg-sv-light border border-sv-primary/20 flex-shrink-0 overflow-hidden flex items-center justify-center">
        {profile?.photo_url ? (
          <img
            src={profile.photo_url}
            alt={profile.full_name ? `${profile.full_name}'s photo` : 'Student photo'}
            className="h-full w-full object-cover"
          />
        ) : (
          <GraduationCap className="h-7 w-7 text-sv-primary" aria-hidden="true" />
        )}
      </div>

      <div className="min-w-0 flex-1">
        {isLoading ? (
          <div className="space-y-2 animate-pulse" aria-hidden="true">
            <div className="h-5 w-40 rounded bg-gray-100" />
            <div className="h-3.5 w-64 rounded bg-gray-100" />
          </div>
        ) : !profile ? (
          <p className="text-sm text-red-500">Couldn't load your profile.</p>
        ) : (
          <>
            <h2 className="text-lg font-bold text-gray-900 leading-tight">
              {getGreeting()}{firstName ? `, ${firstName}` : ''}
            </h2>
            <div className="flex flex-wrap gap-x-4 gap-y-1 mt-1.5">
              {activeSemester && <InfoChip icon={BookOpen} label="Semester" value={String(activeSemester.number)} />}
              {profile.program && <InfoChip icon={GraduationCap} label="Program" value={profile.program.name} />}
              {profile.department && <InfoChip icon={Building2} label="Dept" value={profile.department.name} />}
              {profile.current_section && <InfoChip icon={Users} label="Section" value={profile.current_section.name} />}
            </div>
          </>
        )}
      </div>
    </section>
  )
}
