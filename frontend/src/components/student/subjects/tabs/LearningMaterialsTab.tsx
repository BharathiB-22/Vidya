import { useMemo, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Library, Search, MessageCircle, Send } from 'lucide-react'
import * as learningPackageApi from '@/lib/api/learningPackage'
import type { PackageItem } from '@/types/learningPackage'
import { UnitSelector } from '../UnitSelector'
import type { SubjectTabProps } from './types'

const FILTERS: { key: string; label: string; match: (i: PackageItem) => boolean }[] = [
  { key: 'ALL', label: 'All', match: () => true },
  { key: 'FACULTY_NOTE', label: 'Faculty Notes', match: (i) => i.source_type === 'FACULTY_NOTE' },
  { key: 'REFERENCE_BOOKS', label: 'Reference Books', match: (i) => i.source_type === 'NPTEL' || i.source_type === 'MIT_OCW' },
  { key: 'ARTICLES', label: 'Articles', match: (i) => i.source_type === 'ARXIV' },
  { key: 'VIDEOS', label: 'Videos', match: (i) => i.source_type === 'YOUTUBE' },
  { key: 'AI_CURATED', label: 'AI Curated', match: (i) => !i.faculty_recommended },
  { key: 'DOWNLOADS', label: 'Downloads', match: (i) => !!i.url },
]

interface QATurn {
  question: string
  answer: string
}

export function LearningMaterialsTab({ subject }: SubjectTabProps) {
  const [unit, setUnit] = useState<number | null>(subject.units[0]?.unit_number ?? null)
  const [filter, setFilter] = useState('ALL')
  const [search, setSearch] = useState('')
  const [question, setQuestion] = useState('')
  const [sessionId, setSessionId] = useState<string | undefined>()
  const [turns, setTurns] = useState<QATurn[]>([])

  const { data: pkgList, isLoading: isListLoading } = useQuery({
    queryKey: ['student-learning-packages', subject.syllabus_id, unit],
    queryFn: () => learningPackageApi.studentListPackages(subject.syllabus_id!, unit ?? undefined),
    enabled: !!subject.syllabus_id && unit != null,
  })
  const pkg = pkgList?.items?.[0]

  const { data: items, isLoading: isItemsLoading } = useQuery({
    queryKey: ['learning-package-items', pkg?.id],
    queryFn: () => learningPackageApi.listItems(pkg!.id),
    enabled: !!pkg?.id,
  })

  const filtered = useMemo(() => {
    const list = items ?? []
    const q = search.trim().toLowerCase()
    const active = FILTERS.find((f) => f.key === filter) ?? FILTERS[0]
    return list.filter((i: PackageItem) => active.match(i) && (!q || i.title.toLowerCase().includes(q)))
  }, [items, filter, search])

  const askMutation = useMutation({
    mutationFn: () => learningPackageApi.askQuestion(pkg!.id, question, sessionId),
    onSuccess: (res) => {
      setTurns((t) => [...t, { question, answer: res.answer }])
      setSessionId(res.session_id)
      setQuestion('')
    },
  })

  if (!subject.syllabus_id) {
    return (
      <div className="text-center py-12 rounded-xl border border-dashed border-gray-200">
        <Library className="h-8 w-8 mx-auto mb-2 text-gray-200" />
        <p className="text-sm text-gray-600">No approved syllabus yet — learning materials aren't available.</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <UnitSelector units={subject.units} selected={unit} onSelect={setUnit} />

      {isListLoading ? (
        <div className="text-sm text-gray-600 py-8 text-center">Loading materials…</div>
      ) : !pkg ? (
        <div className="text-center py-12 rounded-xl border border-dashed border-gray-200">
          <Library className="h-8 w-8 mx-auto mb-2 text-gray-200" />
          <p className="text-sm text-gray-600">No learning materials curated for this unit yet.</p>
        </div>
      ) : (
        <>
          <p className="text-xs text-gray-600">
            Looking for slides or PPTs? See the <span className="font-medium text-gray-500">Course Kit</span> tab.
          </p>

          <div className="flex flex-col sm:flex-row gap-3">
            <div className="relative flex-1">
              <Search className="h-4 w-4 text-gray-600 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search materials…"
                className="w-full pl-9 pr-3 py-2 text-sm rounded-lg border border-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div className="flex gap-1.5 overflow-x-auto">
              {FILTERS.map((f) => (
                <button
                  key={f.key}
                  type="button"
                  onClick={() => setFilter(f.key)}
                  className={`shrink-0 text-xs px-3 py-1.5 rounded-full font-medium border transition-colors ${
                    filter === f.key
                      ? 'bg-blue-600 text-white border-blue-600'
                      : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'
                  }`}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>

          {isItemsLoading ? (
            <div className="text-sm text-gray-600 py-8 text-center">Loading items…</div>
          ) : filtered.length === 0 ? (
            <p className="text-sm text-gray-600 py-6 text-center">No materials match this filter.</p>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {filtered.map((item) => (
                <a
                  key={item.id}
                  href={item.url ?? undefined}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="rounded-xl border border-gray-200 bg-white p-4 hover:bg-gray-50 transition-colors block"
                >
                  <div className="flex items-center gap-2 mb-1.5">
                    <span className="text-xs px-1.5 py-0.5 rounded font-medium bg-gray-100 text-gray-600">
                      {item.source_type}
                    </span>
                    {item.faculty_recommended && (
                      <span className="text-xs px-1.5 py-0.5 rounded font-medium bg-amber-50 text-amber-700">
                        Faculty pick
                      </span>
                    )}
                  </div>
                  <p className="text-sm font-medium text-gray-800 line-clamp-2">{item.title}</p>
                </a>
              ))}
            </div>
          )}

          <div className="rounded-xl border border-gray-200 bg-white p-4 space-y-3">
            <h3 className="text-xs font-semibold text-gray-600 uppercase tracking-wide flex items-center gap-1.5">
              <MessageCircle className="h-3.5 w-3.5" /> Notebook Q&amp;A
            </h3>
            {turns.length > 0 && (
              <div className="space-y-2 max-h-64 overflow-y-auto">
                {turns.map((t, i) => (
                  <div key={i} className="text-sm">
                    <p className="font-medium text-gray-800">{t.question}</p>
                    <p className="text-gray-600 mt-0.5">{t.answer}</p>
                  </div>
                ))}
              </div>
            )}
            <form
              onSubmit={(e) => {
                e.preventDefault()
                if (question.trim()) askMutation.mutate()
              }}
              className="flex gap-2"
            >
              <input
                type="text"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="Ask a question about this unit's materials…"
                className="flex-1 px-3 py-2 text-sm rounded-lg border border-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <button
                type="submit"
                disabled={askMutation.isPending || !question.trim()}
                className="px-3 py-2 rounded-lg bg-blue-600 text-white disabled:opacity-40 flex items-center gap-1.5 text-sm"
              >
                <Send className="h-3.5 w-3.5" />
              </button>
            </form>
          </div>
        </>
      )}
    </div>
  )
}
