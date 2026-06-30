import { useState } from 'react'
import { UserCheck, Trash2, Building2, GraduationCap, Star, AlertTriangle } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { PageLoading } from '@/components/shared/PageLoading'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  useDeanPrograms,
  useDeanFacultyAssignments,
  useAssignFacultyToProgram,
  useRemoveFacultyFromProgram,
} from '@/hooks/useOwnership'
import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api'
import type { FacultyProgramAssignmentOut } from '@/lib/api/ownership'

interface FacultyUserItem {
  id:        string
  full_name: string
  email:     string
  role:      string
}

function AssignmentRow({
  row,
  onRemove,
  removing,
}: {
  row: FacultyProgramAssignmentOut
  onRemove: () => void
  removing: boolean
}) {
  return (
    <div className="flex items-center justify-between gap-3 py-3 border-b border-gray-100 last:border-0">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-medium text-gray-900">{row.faculty_name ?? '—'}</span>
          {row.is_primary && (
            <span className="inline-flex items-center gap-1 text-xs text-amber-600 bg-amber-50 border border-amber-100 px-1.5 py-0.5 rounded">
              <Star className="h-2.5 w-2.5" /> Primary
            </span>
          )}
        </div>
        <p className="text-xs text-gray-400 mt-0.5">
          {row.program_name ?? '—'}
          {row.department_name ? ` · ${row.department_name}` : ''}
        </p>
        {row.faculty_email && (
          <p className="text-xs text-gray-400">{row.faculty_email}</p>
        )}
      </div>
      <Button
        variant="ghost"
        size="sm"
        onClick={onRemove}
        disabled={removing}
        className="text-red-400 hover:text-red-600 hover:bg-red-50 flex-shrink-0"
      >
        <Trash2 className="h-3.5 w-3.5" />
      </Button>
    </div>
  )
}

export default function DeanAssignFacultyProgramPage() {
  const [selectedProgram, setSelectedProgram] = useState('')
  const [selectedFaculty, setSelectedFaculty] = useState('')
  const [isPrimary, setIsPrimary]             = useState(false)
  const [formError, setFormError]             = useState<string | null>(null)
  const [removingId, setRemovingId]           = useState<string | null>(null)

  const { data: programs, isLoading: progsLoading } = useDeanPrograms()

  const { data: facultyList, isLoading: facLoading } = useQuery<FacultyUserItem[]>({
    queryKey: ['faculty-list'],
    queryFn:  () => api.get<FacultyUserItem[]>('/course-assignments/faculty-list').then(r => r.data),
    staleTime: 5 * 60 * 1000,
  })

  const { data: assignments, isLoading: assignLoading } = useDeanFacultyAssignments()

  const assign = useAssignFacultyToProgram()
  const remove = useRemoveFacultyFromProgram()

  const filteredAssignments = selectedProgram
    ? assignments?.filter(a => a.program_id === selectedProgram)
    : assignments

  const handleAssign = async () => {
    setFormError(null)
    if (!selectedProgram || !selectedFaculty) {
      setFormError('Please select both a program and a faculty member.')
      return
    }
    try {
      await assign.mutateAsync({
        faculty_user_id: selectedFaculty,
        program_id:      selectedProgram,
        is_primary:      isPrimary,
      })
      setSelectedFaculty('')
      setIsPrimary(false)
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: { message?: string } | string } } })
        ?.response?.data?.detail
      if (typeof msg === 'object' && msg?.message) {
        setFormError(msg.message)
      } else if (typeof msg === 'string') {
        setFormError(msg)
      } else {
        setFormError('Failed to assign faculty. Please try again.')
      }
    }
  }

  const handleRemove = async (id: string) => {
    setRemovingId(id)
    try {
      await remove.mutateAsync(id)
    } finally {
      setRemovingId(null)
    }
  }

  return (
    <PageShell>
      <PageHeader
        title="Faculty Program Assignments"
        subtitle="Assign faculty to programs you govern. Faculty can belong to multiple programs."
        icon={UserCheck}
      />

      {/* Assignment form */}
      <div className="rounded-xl border border-gray-200 bg-white p-5 space-y-4">
        <h3 className="text-sm font-semibold text-gray-700">Assign Faculty to Program</h3>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <p className="text-xs text-gray-500 font-medium">Program</p>
            <Select value={selectedProgram} onValueChange={setSelectedProgram} disabled={progsLoading}>
              <SelectTrigger>
                <SelectValue placeholder="Select program…" />
              </SelectTrigger>
              <SelectContent>
                {programs?.map(p => (
                  <SelectItem key={p.id} value={p.id}>
                    <span className="flex items-center gap-2">
                      <GraduationCap className="h-3.5 w-3.5 text-gray-400" />
                      {p.name}
                      {p.department && (
                        <span className="text-xs text-gray-400 flex items-center gap-1">
                          <Building2 className="h-3 w-3" />
                          {p.department.code}
                        </span>
                      )}
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <p className="text-xs text-gray-500 font-medium">Faculty</p>
            <Select value={selectedFaculty} onValueChange={setSelectedFaculty} disabled={facLoading}>
              <SelectTrigger>
                <SelectValue placeholder="Select faculty…" />
              </SelectTrigger>
              <SelectContent>
                {facultyList?.map((f) => (
                  <SelectItem key={f.id} value={f.id}>
                    {f.full_name}
                    <span className="text-xs text-gray-400 ml-2">{f.email}</span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <label className="flex items-center gap-2 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={isPrimary}
            onChange={e => setIsPrimary(e.target.checked)}
            className="rounded border-gray-300 text-sv-primary focus:ring-sv-primary"
          />
          <span className="text-sm text-gray-600">
            Mark as primary coordinator for this program
          </span>
        </label>

        {formError && (
          <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 border border-red-100 rounded-lg px-3 py-2">
            <AlertTriangle className="h-4 w-4 flex-shrink-0" />
            {formError}
          </div>
        )}

        <Button
          onClick={handleAssign}
          disabled={assign.isPending || !selectedProgram || !selectedFaculty}
          className="w-full sm:w-auto"
        >
          {assign.isPending ? 'Assigning…' : 'Assign Faculty'}
        </Button>
      </div>

      {/* Current assignments table */}
      <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <h3 className="text-sm font-semibold text-gray-700">Current Assignments</h3>
          <Select value={selectedProgram || 'all'} onValueChange={v => setSelectedProgram(v === 'all' ? '' : v)}>
            <SelectTrigger className="w-44 h-8 text-xs">
              <SelectValue placeholder="All Programs" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Programs</SelectItem>
              {programs?.map(p => (
                <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="px-5">
          {(assignLoading) && <PageLoading />}

          {!assignLoading && (!filteredAssignments || filteredAssignments.length === 0) && (
            <div className="py-10 text-center text-sm text-gray-400">
              No assignments yet.
            </div>
          )}

          {filteredAssignments?.map(row => (
            <AssignmentRow
              key={row.id}
              row={row}
              onRemove={() => handleRemove(row.id)}
              removing={removingId === row.id}
            />
          ))}
        </div>
      </div>
    </PageShell>
  )
}
