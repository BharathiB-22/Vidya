import { Loader2, AlertTriangle } from 'lucide-react'

interface AIGeneratingBannerProps {
  isGenerating: boolean
  failed?: boolean
  entity?: string
  /**
   * What the AI is doing right now — "Generating Unit III…", "Creating Course
   * Outcomes…". Written by the job itself, in the words a Board member would use.
   *
   * A syllabus takes ten AI calls and several minutes to write. A spinner across all of
   * it is what makes this feel like a machine being asked for a document; a Board
   * watching the units appear one by one is watching a syllabus being written. That is
   * the whole difference, and it costs one line of text.
   */
  message?: string | null
}

export function AIGeneratingBanner({
  isGenerating,
  failed = false,
  entity = 'content',
  message = null,
}: AIGeneratingBannerProps) {
  if (isGenerating) {
    return (
      <div className="flex items-center gap-2 rounded-lg bg-amber-50 border border-amber-200 px-4 py-3 text-amber-800 text-sm">
        <Loader2 className="h-4 w-4 animate-spin shrink-0" />
        <span>
          {message ? (
            <span className="font-medium">{message}</span>
          ) : (
            <>Writing the official {entity}…</>
          )}
          <span className="ml-1.5 text-amber-700">
            You can leave this page — it will be here when you come back.
          </span>
        </span>
      </div>
    )
  }
  if (failed) {
    return (
      <div className="flex items-center gap-2 rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-red-700 text-sm">
        <AlertTriangle className="h-4 w-4 shrink-0" />
        <span>
          AI generation did not finish. Anything it completed has been kept — regenerate
          the unfinished parts, and nothing you already have will be touched.
        </span>
      </div>
    )
  }
  return null
}
