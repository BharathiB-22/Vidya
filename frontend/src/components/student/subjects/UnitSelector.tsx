import type { SyllabusUnitOut } from '@/lib/api/sis'

interface UnitSelectorProps {
  units: SyllabusUnitOut[]
  selected: number | null
  onSelect: (unitNumber: number) => void
}

export function UnitSelector({ units, selected, onSelect }: UnitSelectorProps) {
  if (units.length === 0) {
    return <p className="text-sm text-gray-400">No units published in the syllabus yet.</p>
  }
  return (
    <div className="flex gap-1.5 overflow-x-auto pb-1">
      {units.map((u) => (
        <button
          key={u.unit_number}
          type="button"
          onClick={() => onSelect(u.unit_number)}
          className={`shrink-0 text-xs px-3 py-1.5 rounded-full font-medium border transition-colors ${
            selected === u.unit_number
              ? 'bg-blue-600 text-white border-blue-600'
              : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'
          }`}
        >
          Unit {u.unit_number}: {u.title}
        </button>
      ))}
    </div>
  )
}
