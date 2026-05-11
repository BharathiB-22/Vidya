import { useState } from 'react'
import { Search, Plus, Trash2, CheckCircle, BookOpen } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  useSearchReferences,
  useAddReference,
  useDeleteReference,
  useConfirmReference,
} from '@/hooks/syllabuses'
import type { ReferenceCandidate, RefType, SyllabusReference, SyllabusReferenceCreate } from '@/types/syllabus'

const REF_TYPE_LABEL: Record<RefType, string> = {
  TEXTBOOK:  'Textbook',
  REFERENCE: 'Reference',
  JOURNAL:   'Journal',
  ONLINE:    'Online',
}

const REF_TYPE_COLOR: Record<RefType, string> = {
  TEXTBOOK:  'bg-blue-100 text-blue-700',
  REFERENCE: 'bg-purple-100 text-purple-700',
  JOURNAL:   'bg-green-100 text-green-700',
  ONLINE:    'bg-orange-100 text-orange-700',
}

interface Props {
  syllabusId:  string
  references:  SyllabusReference[]
  isEditable:  boolean
}

function candidateToCreate(c: ReferenceCandidate): SyllabusReferenceCreate {
  return {
    title:        c.title,
    authors:      c.authors,
    year:         c.year ?? undefined,
    ref_type:     c.ref_type,
    source:       c.source,
    doi:          c.doi ?? undefined,
    isbn:         c.isbn ?? undefined,
    url:          c.url ?? undefined,
    publisher:    c.publisher ?? undefined,
    is_confirmed: false,
  }
}

function RefBadge({ type }: { type: RefType }) {
  return (
    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${REF_TYPE_COLOR[type]}`}>
      {REF_TYPE_LABEL[type]}
    </span>
  )
}

interface SearchPanelProps {
  syllabusId: string
  onAdd: (payload: SyllabusReferenceCreate) => void
  isPending: boolean
}

function SearchPanel({ syllabusId, onAdd, isPending }: SearchPanelProps) {
  const [query, setQuery]     = useState('')
  const [submitted, setSubmitted] = useState('')

  const { data: candidates, isFetching } = useSearchReferences(
    syllabusId,
    submitted ? { query: submitted, limit: 10 } : null,
  )

  function handleSearch(e: React.FormEvent) {
    e.preventDefault()
    setSubmitted(query.trim())
  }

  return (
    <div className="space-y-3 rounded-lg border border-dashed border-gray-300 p-4 bg-gray-50">
      <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Search &amp; Add References</p>
      <form onSubmit={handleSearch} className="flex gap-2">
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search title, author, DOI…"
          className="flex-1"
        />
        <Button type="submit" size="sm" disabled={!query.trim() || isFetching}>
          <Search className="h-4 w-4" />
        </Button>
      </form>

      {isFetching && (
        <p className="text-sm text-gray-400 text-center">Searching…</p>
      )}

      {candidates && candidates.length === 0 && (
        <p className="text-sm text-gray-400 text-center">No results found.</p>
      )}

      {candidates && candidates.length > 0 && (
        <div className="divide-y divide-gray-100 rounded-lg border border-gray-200 bg-white">
          {candidates.map((c, i) => (
            <div key={i} className="flex items-start gap-3 px-3 py-2">
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-800 truncate">{c.title}</p>
                <p className="text-xs text-gray-500">
                  {c.authors.join(', ')}{c.year ? ` · ${c.year}` : ''}
                </p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <RefBadge type={c.ref_type} />
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => onAdd(candidateToCreate(c))}
                  disabled={isPending}
                >
                  <Plus className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export function ReferencesSection({ syllabusId, references, isEditable }: Props) {
  const addRef     = useAddReference(syllabusId)
  const deleteRef  = useDeleteReference(syllabusId)
  const confirmRef = useConfirmReference(syllabusId)

  const confirmed   = references.filter((r) => r.is_confirmed)
  const unconfirmed = references.filter((r) => !r.is_confirmed)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700">
          References ({references.length})
        </h3>
      </div>

      {isEditable && (
        <SearchPanel
          syllabusId={syllabusId}
          onAdd={(payload) => addRef.mutate(payload)}
          isPending={addRef.isPending}
        />
      )}

      {unconfirmed.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-amber-600 uppercase tracking-wide mb-2">
            Pending Confirmation ({unconfirmed.length})
          </p>
          <RefList
            refs={unconfirmed}
            isEditable={isEditable}
            onConfirm={(id) => confirmRef.mutate(id)}
            onDelete={(id) => deleteRef.mutate(id)}
            isPending={deleteRef.isPending || confirmRef.isPending}
          />
        </div>
      )}

      {confirmed.length > 0 && (
        <div>
          {unconfirmed.length > 0 && (
            <p className="text-xs font-semibold text-green-600 uppercase tracking-wide mb-2">
              Confirmed ({confirmed.length})
            </p>
          )}
          <RefList
            refs={confirmed}
            isEditable={isEditable}
            onDelete={(id) => deleteRef.mutate(id)}
            isPending={deleteRef.isPending}
          />
        </div>
      )}

      {references.length === 0 && !isEditable && (
        <p className="text-sm text-gray-400 py-4 text-center">No references.</p>
      )}
    </div>
  )
}

interface RefListProps {
  refs:       SyllabusReference[]
  isEditable: boolean
  onConfirm?: (id: string) => void
  onDelete:   (id: string) => void
  isPending:  boolean
}

function RefList({ refs, isEditable, onConfirm, onDelete, isPending }: RefListProps) {
  return (
    <div className="divide-y divide-gray-100 rounded-lg border border-gray-200">
      {refs.map((ref) => (
        <div key={ref.id} className="flex items-start gap-3 px-4 py-3 hover:bg-gray-50">
          <BookOpen className="h-4 w-4 text-gray-400 shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-gray-800">{ref.title}</p>
            <p className="text-xs text-gray-500">
              {ref.authors.join(', ')}{ref.year ? ` · ${ref.year}` : ''}
              {ref.publisher ? ` · ${ref.publisher}` : ''}
            </p>
            {ref.doi && (
              <p className="text-xs text-blue-600 font-mono">DOI: {ref.doi}</p>
            )}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <RefBadge type={ref.ref_type} />
            {isEditable && onConfirm && !ref.is_confirmed && (
              <Button
                size="icon"
                variant="ghost"
                className="h-7 w-7 text-green-600 hover:text-green-700"
                onClick={() => onConfirm(ref.id)}
                disabled={isPending}
                title="Confirm reference"
              >
                <CheckCircle className="h-3.5 w-3.5" />
              </Button>
            )}
            {isEditable && (
              <Button
                size="icon"
                variant="ghost"
                className="h-7 w-7 text-red-500 hover:text-red-700"
                onClick={() => onDelete(ref.id)}
                disabled={isPending}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
