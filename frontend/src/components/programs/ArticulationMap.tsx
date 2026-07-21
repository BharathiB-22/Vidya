import { useState, useMemo } from 'react'
import { useArticulationMap } from '@/hooks/programs'
import type { Course, Program } from '@/types/program'

const PADDING = 28
const NODE_W = 164
const NODE_H = 52
const H_GAP = 64
const V_GAP = 18

function truncate(s: string, max: number) {
  return s.length > max ? s.slice(0, max - 1) + '…' : s
}

function nodeColors(course: Course) {
  if (course.is_ai_generated) return { fill: '#faf5ff', stroke: '#a855f7' }
  if (course.is_elective)     return { fill: '#fffbeb', stroke: '#f59e0b' }
  return                             { fill: '#eff6ff', stroke: '#3b82f6' }
}

function edgePath(x1: number, y1: number, x2: number, y2: number) {
  if (x1 < x2) {
    const mx = (x1 + x2) / 2
    return `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`
  }
  // backward / same-column: arc above
  const lift = Math.min(y1, y2) - 40
  const mx = (x1 + x2) / 2
  return `M${x1},${y1} C${mx},${lift} ${mx},${lift} ${x2},${y2}`
}

interface Props {
  program: Program
  courses: Course[]
}

export function ArticulationMap({ program, courses }: Props) {
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const { data: mapData, isLoading } = useArticulationMap(program.id, courses)

  const bySemester = useMemo(() => {
    const m = new Map<number, Course[]>()
    courses.forEach(c => {
      if (!m.has(c.semester)) m.set(c.semester, [])
      m.get(c.semester)!.push(c)
    })
    return m
  }, [courses])

  const semesters = useMemo(
    () => Array.from(bySemester.keys()).sort((a, b) => a - b),
    [bySemester],
  )

  const maxPerSem = useMemo(
    () => Math.max(1, ...Array.from(bySemester.values()).map(a => a.length)),
    [bySemester],
  )

  const nodePos = useMemo(() => {
    const pos: Record<string, { x: number; y: number }> = {}
    semesters.forEach((sem, si) => {
      ;(bySemester.get(sem) ?? []).forEach((c, ci) => {
        pos[c.id] = {
          x: PADDING + si * (NODE_W + H_GAP),
          y: PADDING + ci * (NODE_H + V_GAP),
        }
      })
    })
    return pos
  }, [semesters, bySemester])

  const svgW = PADDING * 2 + semesters.length * (NODE_W + H_GAP) - H_GAP
  const svgH = PADDING * 2 + maxPerSem * (NODE_H + V_GAP) - V_GAP
  const totalH = svgH + 32

  function edgeState(edge: { fromId: string; toId: string }) {
    if (!hoveredId) return 'default'
    if (edge.fromId === hoveredId) return 'outgoing'
    if (edge.toId === hoveredId)   return 'incoming'
    return 'dimmed'
  }

  function nodeOpacity(courseId: string) {
    if (!hoveredId || courseId === hoveredId) return 1
    const adj = mapData?.adjacency[hoveredId] ?? []
    const rev = mapData?.reverseAdj[hoveredId] ?? []
    if (adj.includes(courseId) || rev.includes(courseId)) return 1
    return 0.3
  }

  if (courses.length === 0) {
    return (
      <p className="text-sm text-gray-600 text-center py-10">
        No courses defined yet. Add courses via the Structure tab.
      </p>
    )
  }

  const hasEdges = (mapData?.edges.length ?? 0) > 0

  return (
    <div className="space-y-3">
      {/* Legend */}
      <div className="flex flex-wrap items-center gap-4 text-xs text-gray-500">
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-3 rounded border border-blue-400 bg-blue-50" />
          Core
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-3 rounded border border-amber-400 bg-amber-50" />
          Elective
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-3 rounded border border-purple-400 bg-purple-50" />
          AI Generated
        </span>
        {hasEdges && (
          <>
            <span className="flex items-center gap-1.5 ml-2">
              <span className="inline-block w-5 h-0.5 bg-green-500" />
              Outgoing (X requires)
            </span>
            <span className="flex items-center gap-1.5">
              <span className="inline-block w-5 h-0.5 bg-orange-500" />
              Incoming (required by X)
            </span>
          </>
        )}
      </div>

      {/* Canvas */}
      <div className="overflow-auto rounded-lg border border-gray-200 bg-white">
        <svg width={svgW} height={totalH} className="block">
          <defs>
            <marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto">
              <path d="M0 0L10 5L0 10z" fill="#94a3b8" />
            </marker>
            <marker id="arr-g" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto">
              <path d="M0 0L10 5L0 10z" fill="#22c55e" />
            </marker>
            <marker id="arr-o" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto">
              <path d="M0 0L10 5L0 10z" fill="#f97316" />
            </marker>
          </defs>

          {/* Semester column labels */}
          {semesters.map((sem, si) => (
            <text
              key={sem}
              x={PADDING + si * (NODE_W + H_GAP) + NODE_W / 2}
              y={svgH + 20}
              textAnchor="middle"
              style={{ fontSize: 11, fill: '#94a3b8' }}
            >
              Semester {sem}
            </text>
          ))}

          {/* Edges */}
          {!isLoading &&
            mapData?.edges.map((edge, i) => {
              const from = nodePos[edge.fromId]
              const to   = nodePos[edge.toId]
              if (!from || !to) return null
              const st = edgeState(edge)
              const x1 = from.x + NODE_W
              const y1 = from.y + NODE_H / 2
              const x2 = to.x
              const y2 = to.y + NODE_H / 2
              const stroke  = st === 'outgoing' ? '#22c55e' : st === 'incoming' ? '#f97316' : '#94a3b8'
              const marker  = st === 'outgoing' ? 'url(#arr-g)' : st === 'incoming' ? 'url(#arr-o)' : 'url(#arr)'
              const opacity = st === 'dimmed' ? 0.12 : 1
              const sw      = st === 'default' || st === 'dimmed' ? 1.5 : 2
              return (
                <path
                  key={i}
                  d={edgePath(x1, y1, x2, y2)}
                  fill="none"
                  stroke={stroke}
                  strokeWidth={sw}
                  opacity={opacity}
                  markerEnd={marker}
                />
              )
            })}

          {/* Nodes */}
          {courses.map(course => {
            const pos = nodePos[course.id]
            if (!pos) return null
            const isHovered = hoveredId === course.id
            const { fill, stroke } = nodeColors(course)
            const opacity = nodeOpacity(course.id)
            return (
              <g
                key={course.id}
                transform={`translate(${pos.x},${pos.y})`}
                opacity={opacity}
                onMouseEnter={() => setHoveredId(course.id)}
                onMouseLeave={() => setHoveredId(null)}
                style={{ cursor: 'default' }}
              >
                <rect
                  width={NODE_W}
                  height={NODE_H}
                  rx={6}
                  fill={fill}
                  stroke={isHovered ? stroke : '#e2e8f0'}
                  strokeWidth={isHovered ? 2 : 1}
                />
                <text x={10} y={20} style={{ fontSize: 11, fontWeight: 700, fill: '#1e293b' }}>
                  {course.code}
                </text>
                <text x={10} y={36} style={{ fontSize: 10, fill: '#64748b' }}>
                  {truncate(course.title, 23)} · {course.credits}cr
                </text>
              </g>
            )
          })}
        </svg>
      </div>

      {!isLoading && !hasEdges && (
        <p className="text-xs text-gray-600 text-center py-1">
          No prerequisite relationships defined. Add prerequisites when editing a course.
        </p>
      )}
    </div>
  )
}
