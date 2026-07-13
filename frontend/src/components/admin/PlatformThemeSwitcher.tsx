import { useEffect, useRef, useState } from 'react'
import { Check, Palette } from 'lucide-react'
import {
  PLATFORM_THEMES,
  PLATFORM_THEME_LABELS,
  usePlatformTheme,
  type PlatformTheme,
} from '@/lib/platformTheme'

/**
 * Theme selector for the Platform Console header.
 *
 * Styled entirely from --pc-* tokens, so the control itself re-themes along
 * with the console it controls.
 */
export function PlatformThemeSwitcher() {
  const { theme, setTheme } = usePlatformTheme()
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return

    function onPointerDown(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false)
    }

    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  function choose(next: PlatformTheme) {
    setTheme(next)
    setOpen(false)
  }

  return (
    <div ref={rootRef} className="relative flex-shrink-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Theme: ${PLATFORM_THEME_LABELS[theme].name}`}
        title={`Theme: ${PLATFORM_THEME_LABELS[theme].name}`}
        className="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-[12px] font-medium transition-colors"
        style={{
          background: open ? 'var(--pc-fill-strong)' : 'transparent',
          border: '1px solid var(--pc-border)',
          color: 'var(--pc-slate-300)',
        }}
        onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--pc-fill)' }}
        onMouseLeave={(e) => {
          e.currentTarget.style.background = open ? 'var(--pc-fill-strong)' : 'transparent'
        }}
      >
        <Palette className="h-[15px] w-[15px] flex-shrink-0" style={{ color: 'var(--pc-slate-400)' }} />
        <span aria-hidden className="text-[13px] leading-none">
          {PLATFORM_THEME_LABELS[theme].swatch}
        </span>
        <span className="hidden md:inline">{PLATFORM_THEME_LABELS[theme].name}</span>
      </button>

      {open && (
        <div
          role="menu"
          aria-label="Console theme"
          className="absolute right-0 top-full mt-1.5 w-44 rounded-xl p-1 z-50 overflow-hidden"
          style={{
            background: 'var(--pc-elevated)',
            border: '1px solid var(--pc-border-strong)',
            boxShadow: '0 12px 32px rgba(0,0,0,0.28)',
          }}
        >
          <p
            className="px-2.5 pt-1.5 pb-1 text-[9px] font-bold uppercase tracking-[0.14em]"
            style={{ color: 'var(--pc-slate-600)' }}
          >
            Console theme
          </p>

          {PLATFORM_THEMES.map((option) => {
            const selected = option === theme
            const { name, swatch } = PLATFORM_THEME_LABELS[option]
            return (
              <button
                key={option}
                type="button"
                role="menuitemradio"
                aria-checked={selected}
                onClick={() => choose(option)}
                className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-sm font-medium transition-colors text-left"
                style={{
                  background: selected ? 'var(--pc-accent-soft)' : 'transparent',
                  color: selected ? 'var(--pc-accent-text)' : 'var(--pc-slate-300)',
                }}
                onMouseEnter={(e) => {
                  if (!selected) e.currentTarget.style.background = 'var(--pc-fill)'
                }}
                onMouseLeave={(e) => {
                  if (!selected) e.currentTarget.style.background = 'transparent'
                }}
              >
                <span aria-hidden className="text-[14px] leading-none">{swatch}</span>
                <span className="flex-1">{name}</span>
                {selected && <Check className="h-3.5 w-3.5 flex-shrink-0" />}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
