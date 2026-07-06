import { useState } from 'react'
import { ChevronLeft, ChevronRight, Presentation } from 'lucide-react'
import type { KitSlide, SlideContent } from '@/types/courseKit'

export function SlideViewer({ slides }: { slides: KitSlide[] }) {
  const [index, setIndex] = useState(0)

  if (slides.length === 0) {
    return (
      <div className="text-center py-12 rounded-xl border border-dashed border-gray-200">
        <Presentation className="h-8 w-8 mx-auto mb-2 text-gray-200" />
        <p className="text-sm text-gray-400">No slides in this kit yet.</p>
      </div>
    )
  }

  const slide = slides[index]
  const content = (slide.content ?? {}) as Partial<SlideContent>

  return (
    <div className="space-y-3">
      <div className="rounded-xl border border-gray-200 bg-white p-6 min-h-[260px]">
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs text-gray-400">Slide {slide.slide_number} of {slides.length}</span>
          {slide.bloom_level && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 font-medium">{slide.bloom_level}</span>
          )}
        </div>
        <h3 className="text-lg font-bold text-gray-900 mb-3">{slide.title}</h3>

        {!!content.bullets?.length && (
          <ul className="list-disc list-inside space-y-1 text-sm text-gray-700 mb-3">
            {content.bullets.map((b, i) => <li key={i}>{b}</li>)}
          </ul>
        )}
        {!!content.key_concepts?.length && (
          <div className="mb-3">
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1">Key concepts</p>
            <div className="flex flex-wrap gap-1.5">
              {content.key_concepts.map((k, i) => (
                <span key={i} className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">{k}</span>
              ))}
            </div>
          </div>
        )}
        {content.code_snippet && (
          <pre className="text-xs bg-gray-900 text-gray-100 rounded-lg p-3 overflow-x-auto mb-3"><code>{content.code_snippet}</code></pre>
        )}
        {!!content.examples?.length && (
          <div className="mb-3">
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1">Examples</p>
            <ul className="list-disc list-inside space-y-1 text-sm text-gray-700">
              {content.examples.map((e, i) => <li key={i}>{e}</li>)}
            </ul>
          </div>
        )}
        {content.student_summary && (
          <p className="text-sm text-gray-500 italic border-t border-gray-100 pt-3 mt-3">{content.student_summary}</p>
        )}
      </div>

      <div className="flex items-center justify-between">
        <button
          type="button"
          disabled={index === 0}
          onClick={() => setIndex((i) => Math.max(0, i - 1))}
          className="flex items-center gap-1 text-sm px-3 py-1.5 rounded-lg border border-gray-200 disabled:opacity-40 hover:bg-gray-50"
        >
          <ChevronLeft className="h-4 w-4" /> Previous
        </button>
        <div className="flex gap-1">
          {slides.map((_, i) => (
            <button
              key={i}
              type="button"
              onClick={() => setIndex(i)}
              className={`h-1.5 w-1.5 rounded-full ${i === index ? 'bg-blue-600' : 'bg-gray-200'}`}
            />
          ))}
        </div>
        <button
          type="button"
          disabled={index === slides.length - 1}
          onClick={() => setIndex((i) => Math.min(slides.length - 1, i + 1))}
          className="flex items-center gap-1 text-sm px-3 py-1.5 rounded-lg border border-gray-200 disabled:opacity-40 hover:bg-gray-50"
        >
          Next <ChevronRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}
