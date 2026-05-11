import { useMemo } from 'react'
import { useCOPOMatrix, useUpdateCOPOMappings } from '@/hooks/syllabuses'
import type { MappingStrength } from '@/types/syllabus'

const CYCLE: (MappingStrength | null)[] = [null, 'LOW', 'MEDIUM', 'HIGH']

const STRENGTH_STYLE: Record<string, string> = {
  LOW:    'bg-green-100 text-green-700 font-semibold',
  MEDIUM: 'bg-yellow-100 text-yellow-700 font-semibold',
  HIGH:   'bg-orange-100 text-orange-700 font-semibold',
}

interface Props {
  syllabusId: string
  isEditable: boolean
}

export function COPOMatrix({ syllabusId, isEditable }: Props) {
  const { data, isLoading, isError } = useCOPOMatrix(syllabusId)
  const updateMappings = useUpdateCOPOMappings(syllabusId)

  const mappingIndex = useMemo(() => {
    const idx: Record<string, Record<string, MappingStrength | null>> = {}
    if (!data) return idx
    for (const row of data.rows) {
      idx[row.co_id] = {}
      for (const cell of row.cells) {
        idx[row.co_id][cell.po_id] = cell.mapping_strength
      }
    }
    return idx
  }, [data])

  if (isLoading) return <p className="text-sm text-gray-400 py-4 text-center">Loading matrix…</p>
  if (isError || !data) return <p className="text-sm text-red-500 py-4">Failed to load CO-PO matrix.</p>
  if (data.rows.length === 0) return (
    <p className="text-sm text-gray-400 py-4 text-center">Add course outcomes first to build the CO-PO matrix.</p>
  )

  function cycleStrength(coId: string, poId: string) {
    if (!isEditable) return
    const current = mappingIndex[coId]?.[poId] ?? null
    const idx = CYCLE.indexOf(current)
    const next = CYCLE[(idx + 1) % CYCLE.length]
    const mappings = data!.rows.find((r) => r.co_id === coId)?.cells
      .filter((c) => c.po_id !== poId && c.mapping_strength != null)
      .map((c) => ({ po_id: c.po_id, mapping_strength: c.mapping_strength!, justification: c.justification ?? undefined })) ?? []
    if (next != null) {
      mappings.push({ po_id: poId, mapping_strength: next, justification: undefined })
    }
    updateMappings.mutate({ coId, payload: { mappings } })
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-gray-200">
      <table className="min-w-full text-xs">
        <thead className="bg-gray-50 border-b border-gray-200">
          <tr>
            <th className="sticky left-0 bg-gray-50 px-3 py-2 text-left font-semibold text-gray-600 w-36">CO / PO</th>
            {data.po_headers.map((po) => (
              <th key={po.po_id} className="px-2 py-2 text-center font-semibold text-gray-600 min-w-[4rem]" title={po.po_description}>
                {po.po_code}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {data.rows.map((row) => (
            <tr key={row.co_id} className="hover:bg-gray-50">
              <td className="sticky left-0 bg-white px-3 py-2 font-semibold text-gray-800 border-r border-gray-100 whitespace-nowrap">
                {row.co_code}
              </td>
              {data.po_headers.map((po) => {
                const strength = mappingIndex[row.co_id]?.[po.po_id] ?? null
                return (
                  <td key={po.po_id} className="text-center px-2 py-2">
                    <button
                      type="button"
                      onClick={() => cycleStrength(row.co_id, po.po_id)}
                      disabled={!isEditable || updateMappings.isPending}
                      className={`w-14 h-7 rounded text-xs transition-colors ${
                        strength
                          ? STRENGTH_STYLE[strength]
                          : 'text-gray-300 hover:bg-gray-100'
                      } ${isEditable ? 'cursor-pointer' : 'cursor-default'}`}
                      title={strength ?? '—'}
                    >
                      {strength ? strength[0] : '—'}
                    </button>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {isEditable && (
        <p className="text-xs text-gray-400 px-3 py-2 border-t border-gray-100">
          Click a cell to cycle: — → L → M → H → —
        </p>
      )}
    </div>
  )
}
