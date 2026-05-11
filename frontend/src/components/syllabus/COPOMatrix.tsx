import { useMemo } from 'react'
import { Loader2 } from 'lucide-react'
import { useCOPOMatrix, useUpdateCOPOMappings } from '@/hooks/syllabuses'
import type { MappingStrength } from '@/types/syllabus'

const CYCLE: (MappingStrength | null)[] = [null, 'LOW', 'MEDIUM', 'HIGH']

// Full-width colored cell styles
const CELL_STYLE: Record<string, string> = {
  HIGH:   'bg-orange-500 text-white',
  MEDIUM: 'bg-yellow-400 text-gray-900',
  LOW:    'bg-green-400 text-gray-900',
}
const CELL_LABEL: Record<string, string> = {
  HIGH: 'H', MEDIUM: 'M', LOW: 'L',
}
const CELL_TITLE: Record<string, string> = {
  HIGH:   'High (3) — click to clear',
  MEDIUM: 'Medium (2) — click to set High',
  LOW:    'Low (1) — click to set Medium',
}

interface Props {
  syllabusId: string
  isEditable: boolean
}

export function COPOMatrix({ syllabusId, isEditable }: Props) {
  const { data, isLoading, isError } = useCOPOMatrix(syllabusId)
  const updateMappings = useUpdateCOPOMappings(syllabusId)

  // Build a fast lookup: coId → poId → strength
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

  // Per-CO mapping count (for summary column)
  const coMappingCount = useMemo(() => {
    const counts: Record<string, number> = {}
    if (!data) return counts
    for (const row of data.rows) {
      counts[row.co_id] = row.cells.filter((c) => c.mapping_strength != null).length
    }
    return counts
  }, [data])

  // Per-PO mapping count (for summary footer row)
  const poMappingCount = useMemo(() => {
    const counts: Record<string, number> = {}
    if (!data) return counts
    for (const po of data.po_headers) {
      counts[po.po_id] = data.rows.filter(
        (r) => mappingIndex[r.co_id]?.[po.po_id] != null,
      ).length
    }
    return counts
  }, [data, mappingIndex])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12 gap-2 text-gray-400">
        <Loader2 className="h-5 w-5 animate-spin" />
        <span className="text-sm">Loading matrix…</span>
      </div>
    )
  }

  if (isError || !data) {
    return <p className="text-sm text-red-500 py-4">Failed to load CO-PO matrix.</p>
  }

  if (data.rows.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-gray-300 py-12 text-center">
        <p className="text-sm text-gray-400">
          Add course outcomes first to build the CO-PO matrix.
        </p>
      </div>
    )
  }

  if (data.po_headers.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-gray-300 py-12 text-center">
        <p className="text-sm text-gray-400">
          No programme outcomes defined. CO-PO matrix unavailable.
        </p>
      </div>
    )
  }

  function cycleStrength(coId: string, poId: string) {
    if (!isEditable || updateMappings.isPending) return
    const current = mappingIndex[coId]?.[poId] ?? null
    const idx = CYCLE.indexOf(current)
    const next = CYCLE[(idx + 1) % CYCLE.length]
    const existing = data!.rows.find((r) => r.co_id === coId)?.cells
      .filter((c) => c.po_id !== poId && c.mapping_strength != null)
      .map((c) => ({
        po_id:            c.po_id,
        mapping_strength: c.mapping_strength!,
        justification:    c.justification ?? undefined,
      })) ?? []
    if (next != null) {
      existing.push({ po_id: poId, mapping_strength: next, justification: undefined })
    }
    updateMappings.mutate({ coId, payload: { mappings: existing } })
  }

  const totalCOs = data.rows.length
  const coveredCOs = data.rows.filter((r) => coMappingCount[r.co_id] > 0).length
  const coveragePct = totalCOs > 0 ? Math.round((coveredCOs / totalCOs) * 100) : 0

  return (
    <div className="space-y-4">
      {/* Coverage summary bar */}
      <div className="flex items-center gap-4 rounded-lg bg-gray-50 border border-gray-200 px-4 py-2.5">
        <div className="flex-1">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs text-gray-500">CO coverage</span>
            <span className="text-xs font-semibold text-gray-700">{coveredCOs}/{totalCOs} COs mapped</span>
          </div>
          <div className="h-1.5 rounded-full bg-gray-200 overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${coveragePct >= 80 ? 'bg-green-500' : coveragePct >= 50 ? 'bg-yellow-400' : 'bg-red-400'}`}
              style={{ width: `${coveragePct}%` }}
            />
          </div>
        </div>
        <span className={`text-sm font-bold ${coveragePct >= 80 ? 'text-green-600' : coveragePct >= 50 ? 'text-yellow-600' : 'text-red-600'}`}>
          {coveragePct}%
        </span>
        {updateMappings.isPending && (
          <Loader2 className="h-4 w-4 animate-spin text-gray-400" />
        )}
      </div>

      {/* Matrix table */}
      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="min-w-full border-collapse text-xs">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-200">
              <th className="sticky left-0 z-10 bg-gray-50 px-3 py-2.5 text-left font-semibold text-gray-600 min-w-[6rem] border-r border-gray-200">
                CO ↓ / PO →
              </th>
              {data.po_headers.map((po) => (
                <th
                  key={po.po_id}
                  className="px-1.5 py-2.5 text-center font-semibold text-gray-600 min-w-[3.5rem]"
                  title={po.po_description}
                >
                  <span className="block">{po.po_code}</span>
                </th>
              ))}
              <th className="px-2 py-2.5 text-center font-semibold text-gray-500 min-w-[3rem] border-l border-gray-200">
                #POs
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {data.rows.map((row) => (
              <tr key={row.co_id} className="hover:bg-gray-50 group">
                <td className="sticky left-0 z-10 bg-white group-hover:bg-gray-50 border-r border-gray-200 px-3 py-2 whitespace-nowrap">
                  <span className="font-semibold text-gray-800">{row.co_code}</span>
                  <span
                    className="ml-1 text-gray-400 font-normal truncate max-w-[8rem] inline-block align-bottom"
                    title={row.description}
                  >
                    — {row.description.substring(0, 30)}{row.description.length > 30 ? '…' : ''}
                  </span>
                </td>
                {data.po_headers.map((po) => {
                  const strength = mappingIndex[row.co_id]?.[po.po_id] ?? null
                  return (
                    <td key={po.po_id} className="p-1 text-center">
                      <button
                        type="button"
                        onClick={() => cycleStrength(row.co_id, po.po_id)}
                        disabled={!isEditable || updateMappings.isPending}
                        title={
                          strength
                            ? CELL_TITLE[strength]
                            : isEditable ? 'No mapping — click to set Low' : 'No mapping'
                        }
                        className={`w-full h-7 rounded font-semibold transition-all text-[11px] tracking-wide ${
                          strength
                            ? CELL_STYLE[strength]
                            : 'bg-gray-100 text-gray-300'
                        } ${isEditable && !updateMappings.isPending ? 'cursor-pointer hover:opacity-90 active:scale-95' : 'cursor-default'}`}
                      >
                        {strength ? CELL_LABEL[strength] : '·'}
                      </button>
                    </td>
                  )
                })}
                <td className="px-2 py-2 text-center border-l border-gray-200">
                  <span className={`text-xs font-semibold ${coMappingCount[row.co_id] > 0 ? 'text-gray-700' : 'text-gray-300'}`}>
                    {coMappingCount[row.co_id]}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="border-t-2 border-gray-200 bg-gray-50">
              <td className="sticky left-0 bg-gray-50 px-3 py-2 text-xs font-semibold text-gray-500 border-r border-gray-200">
                #COs mapped
              </td>
              {data.po_headers.map((po) => (
                <td key={po.po_id} className="py-2 text-center">
                  <span className={`text-xs font-semibold ${poMappingCount[po.po_id] > 0 ? 'text-gray-700' : 'text-gray-300'}`}>
                    {poMappingCount[po.po_id]}
                  </span>
                </td>
              ))}
              <td className="border-l border-gray-200" />
            </tr>
          </tfoot>
        </table>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 text-xs text-gray-500 flex-wrap">
        {isEditable && <span className="text-gray-400">Click a cell to cycle:</span>}
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-5 h-5 rounded bg-orange-500" />
          <span>H — High (3)</span>
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-5 h-5 rounded bg-yellow-400" />
          <span>M — Medium (2)</span>
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-5 h-5 rounded bg-green-400" />
          <span>L — Low (1)</span>
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-5 h-5 rounded bg-gray-100 border border-gray-200" />
          <span>· — Not mapped</span>
        </span>
      </div>
    </div>
  )
}
