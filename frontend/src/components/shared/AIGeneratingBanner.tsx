import { Loader2, AlertTriangle } from 'lucide-react'

interface AIGeneratingBannerProps {
  isGenerating: boolean
  failed?: boolean
  entity?: string
}

export function AIGeneratingBanner({
  isGenerating,
  failed = false,
  entity = 'content',
}: AIGeneratingBannerProps) {
  if (isGenerating) {
    return (
      <div className="flex items-center gap-2 rounded-lg bg-amber-50 border border-amber-200 px-4 py-3 text-amber-700 text-sm">
        <Loader2 className="h-4 w-4 animate-spin shrink-0" />
        <span>AI is generating the {entity}. This page refreshes automatically every 5 s.</span>
      </div>
    )
  }
  if (failed) {
    return (
      <div className="flex items-center gap-2 rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-red-700 text-sm">
        <AlertTriangle className="h-4 w-4 shrink-0" />
        <span>
          AI generation did not complete. The {entity} has been reset to Draft.{' '}
          Check AI provider configuration or quota, then use <strong>Generate with AI</strong> to retry.
        </span>
      </div>
    )
  }
  return null
}
