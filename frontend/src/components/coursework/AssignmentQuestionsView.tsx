import { useState } from 'react'
import { Download, FileText } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { addToast } from '@/hooks/useToast'
import { getErrorMessage } from '@/lib/api'
import type { CourseworkQuestion } from '@/types/coursework'

export interface AssignmentQuestionsViewProps {
  questions: CourseworkQuestion[]
  /** True when a question paper was uploaded instead of structured questions. */
  hasQuestionPaper?: boolean
  /** Resolves a fresh presigned URL for the uploaded question paper. */
  fetchQuestionPaperUrl?: () => Promise<{ url: string }>
}

/**
 * Read-only rendering of an assignment's questions, shared by the student and
 * faculty detail views. Shows the structured questions when present, otherwise a
 * download for the uploaded question paper — and nothing at all for older
 * metadata-only assignments, which keep working untouched.
 */
export function AssignmentQuestionsView({
  questions,
  hasQuestionPaper,
  fetchQuestionPaperUrl,
}: AssignmentQuestionsViewProps) {
  const [downloading, setDownloading] = useState(false)

  async function handleDownload() {
    if (!fetchQuestionPaperUrl) return
    setDownloading(true)
    try {
      const { url } = await fetchQuestionPaperUrl()
      window.open(url, '_blank', 'noopener,noreferrer')
    } catch (err) {
      addToast(getErrorMessage(err), 'error')
    } finally {
      setDownloading(false)
    }
  }

  if (questions.length === 0 && !hasQuestionPaper) return null

  const total = questions.reduce((sum, q) => sum + (Number(q.marks) || 0), 0)

  return (
    <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
      <div className="px-4 py-2.5 border-b border-gray-100 bg-gray-50 flex items-center justify-between">
        <span className="text-xs font-semibold text-gray-600 uppercase tracking-wide">Questions</span>
        {questions.length > 0 && (
          <span className="text-xs text-gray-500">{questions.length} question{questions.length > 1 ? 's' : ''} · {total} marks</span>
        )}
      </div>

      {questions.length > 0 ? (
        <ol className="divide-y divide-gray-100">
          {questions.map((q) => (
            <li key={q.question_number} className="px-4 py-3">
              <div className="flex items-start justify-between gap-3">
                <p className="text-sm text-gray-800 leading-relaxed whitespace-pre-wrap">
                  <span className="font-semibold text-gray-500 mr-2">Q{q.question_number}.</span>
                  {q.question_text}
                </p>
                <span className="text-xs font-medium text-gray-600 whitespace-nowrap shrink-0">{q.marks} marks</span>
              </div>
              {q.notes && <p className="text-xs text-gray-500 mt-1 italic ml-6 whitespace-pre-wrap">{q.notes}</p>}
            </li>
          ))}
        </ol>
      ) : (
        <div className="px-4 py-3 flex items-center gap-3">
          <FileText className="h-5 w-5 text-purple-400 shrink-0" />
          <span className="text-sm text-gray-700 flex-1">A question paper has been provided for this assignment.</span>
          {fetchQuestionPaperUrl && (
            <Button variant="outline" size="sm" onClick={handleDownload} disabled={downloading}>
              <Download className="h-3.5 w-3.5 mr-1.5" />
              {downloading ? 'Opening…' : 'Question paper'}
            </Button>
          )}
        </div>
      )}
    </div>
  )
}
