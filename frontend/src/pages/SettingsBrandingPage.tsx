import { useState, useEffect } from 'react'
import { Palette, Save, CheckCircle2, Info } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useAuth } from '@/lib/auth'

const LS_LOGO  = 'vidya_institution_logo'
const LS_COLOR = 'vidya_institution_color'
const LS_COLOR2 = 'vidya_institution_color2'

function prettifySlug(slug: string): string {
  if (!slug) return 'Your Institution'
  return slug.split('-').map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')
}

function getInitials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .map((w) => w[0].toUpperCase())
    .slice(0, 2)
    .join('')
}

function SidebarPreview({
  institutionName,
  logoUrl,
  primaryColor,
}: {
  institutionName: string
  logoUrl: string
  primaryColor: string
}) {
  const navItems = ['Dashboard', 'Programs', 'Syllabuses', 'Exam Papers']
  const initials = getInitials(institutionName) || 'IN'

  return (
    <div className="rounded-xl border border-gray-200 overflow-hidden shadow-sm" style={{ maxWidth: 200 }}>
      {/* Header */}
      <div className="px-3 py-3 flex items-center gap-2" style={{ backgroundColor: '#0f2044' }}>
        {logoUrl ? (
          <img
            src={logoUrl}
            alt=""
            className="w-7 h-7 rounded-lg object-contain bg-white p-0.5 flex-shrink-0"
            onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
          />
        ) : (
          <div
            className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 text-white font-extrabold text-[10px]"
            style={{ backgroundColor: primaryColor }}
          >
            {initials}
          </div>
        )}
        <div className="min-w-0">
          <p className="text-[11px] font-bold text-white leading-none truncate">{institutionName}</p>
          <p className="text-[9px] text-slate-400 truncate mt-0.5">VIDYA AI Workspace</p>
        </div>
      </div>

      {/* Nav items */}
      <div className="px-2 py-2 space-y-0.5" style={{ backgroundColor: '#0f2044' }}>
        {navItems.map((item, i) => (
          <div
            key={item}
            className="flex items-center gap-2 px-2 py-1.5 rounded-md text-[11px] font-medium"
            style={{
              backgroundColor: i === 0 ? primaryColor : 'transparent',
              color: i === 0 ? '#fff' : '#94a3b8',
            }}
          >
            <div
              className="w-[11px] h-[11px] rounded-sm flex-shrink-0"
              style={{ backgroundColor: i === 0 ? 'rgba(255,255,255,0.3)' : '#334155' }}
            />
            {item}
          </div>
        ))}
      </div>

      {/* Footer */}
      <div className="px-3 py-2 border-t border-white/5" style={{ backgroundColor: '#0f2044' }}>
        <p className="text-[8px] text-slate-600 font-bold tracking-widest uppercase">
          Powered by VIDYA AI
        </p>
      </div>
    </div>
  )
}

export default function SettingsBrandingPage() {
  const { user } = useAuth()
  const institutionName = prettifySlug(user?.tenantSlug ?? '')

  const [logoUrl,      setLogoUrl]      = useState('')
  const [primaryColor, setPrimaryColor] = useState('#2563eb')
  const [secondaryColor, setSecondaryColor] = useState('#06b6d4')
  const [saved,        setSaved]        = useState(false)

  // Load from localStorage on mount
  useEffect(() => {
    const logo  = localStorage.getItem(LS_LOGO)  ?? ''
    const color = localStorage.getItem(LS_COLOR) ?? '#2563eb'
    const color2 = localStorage.getItem(LS_COLOR2) ?? '#06b6d4'
    setLogoUrl(logo)
    setPrimaryColor(color)
    setSecondaryColor(color2)
  }, [])

  function handleSave(e: React.FormEvent) {
    e.preventDefault()
    localStorage.setItem(LS_LOGO,  logoUrl.trim())
    localStorage.setItem(LS_COLOR, primaryColor)
    localStorage.setItem(LS_COLOR2, secondaryColor)
    setSaved(true)
    setTimeout(() => setSaved(false), 3000)
  }

  function handleReset() {
    localStorage.removeItem(LS_LOGO)
    localStorage.removeItem(LS_COLOR)
    localStorage.removeItem(LS_COLOR2)
    setLogoUrl('')
    setPrimaryColor('#2563eb')
    setSecondaryColor('#06b6d4')
  }

  return (
    <div className="max-w-3xl mx-auto px-6 py-8 space-y-6">

      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="p-2 rounded-lg bg-sv-light border border-sv-primary/20">
          <Palette className="h-5 w-5 text-sv-primary" />
        </div>
        <div>
          <h1 className="text-xl font-bold text-gray-900">Institution Branding</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Personalize your institution's Academic AI Workspace — logo, colors, and identity
          </p>
        </div>
      </div>

      {/* Info banner */}
      <div className="flex items-start gap-3 rounded-xl border border-blue-100 bg-blue-50 px-4 py-3">
        <Info className="h-4 w-4 text-blue-500 flex-shrink-0 mt-0.5" />
        <p className="text-xs text-blue-700 leading-relaxed">
          Branding applies to <strong>this institution only</strong> and is previewed in your browser.
          To sync across all devices for your institution, contact your Platform Administrator via the VIDYA AI Platform Console.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">

        {/* Form */}
        <div className="lg:col-span-3">
          <form onSubmit={handleSave} className="bg-white rounded-xl border border-gray-200 p-6 space-y-5">

            {/* Institution info (read-only) */}
            <div className="space-y-3">
              <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Institution</h2>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="block text-sm font-medium text-gray-700">Display name</label>
                  <Input value={institutionName} readOnly className="bg-gray-50 text-gray-500" />
                </div>
                <div className="space-y-1">
                  <label className="block text-sm font-medium text-gray-700">Institution ID</label>
                  <Input value={user?.tenantSlug ?? '—'} readOnly className="bg-gray-50 text-gray-500 font-mono text-sm" />
                </div>
              </div>
            </div>

            {/* Logo */}
            <div className="space-y-1">
              <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Institution Logo</h2>
              <label className="block text-sm font-medium text-gray-700" htmlFor="logo-url">
                Logo URL
              </label>
              <Input
                id="logo-url"
                type="url"
                value={logoUrl}
                onChange={(e) => setLogoUrl(e.target.value)}
                placeholder="https://your-university.edu/logo.png"
              />
              <p className="text-xs text-gray-400">
                PNG or SVG recommended · Appears in the sidebar header for all users of your institution.
                Direct upload coming soon — for now, host your logo and paste the URL.
              </p>
            </div>

            {/* Colors */}
            <div className="space-y-3">
              <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Brand colors</h2>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="block text-sm font-medium text-gray-700" htmlFor="primary-color">
                    Primary color
                  </label>
                  <div className="flex items-center gap-2">
                    <input
                      id="primary-color"
                      type="color"
                      value={primaryColor}
                      onChange={(e) => setPrimaryColor(e.target.value)}
                      className="w-9 h-9 rounded-lg border border-gray-200 cursor-pointer p-0.5 bg-white"
                    />
                    <Input
                      value={primaryColor}
                      onChange={(e) => setPrimaryColor(e.target.value)}
                      placeholder="#2563eb"
                      className="font-mono text-sm"
                      maxLength={7}
                    />
                  </div>
                  <p className="text-xs text-gray-400">Active nav items, buttons</p>
                </div>
                <div className="space-y-1">
                  <label className="block text-sm font-medium text-gray-700" htmlFor="secondary-color">
                    Secondary / Accent
                  </label>
                  <div className="flex items-center gap-2">
                    <input
                      id="secondary-color"
                      type="color"
                      value={secondaryColor}
                      onChange={(e) => setSecondaryColor(e.target.value)}
                      className="w-9 h-9 rounded-lg border border-gray-200 cursor-pointer p-0.5 bg-white"
                    />
                    <Input
                      value={secondaryColor}
                      onChange={(e) => setSecondaryColor(e.target.value)}
                      placeholder="#06b6d4"
                      className="font-mono text-sm"
                      maxLength={7}
                    />
                  </div>
                  <p className="text-xs text-gray-400">Accent indicators, AI badges</p>
                </div>
              </div>
            </div>

            {saved && (
              <div className="flex items-center gap-2 text-sm text-green-700 bg-green-50 border border-green-200 rounded-lg px-3 py-2">
                <CheckCircle2 className="h-4 w-4 flex-shrink-0" />
                Branding saved. Reload to see changes in sidebar.
              </div>
            )}

            <div className="flex gap-3 pt-1">
              <Button type="submit" className="gap-1.5">
                <Save className="h-4 w-4" />
                Save branding
              </Button>
              <Button type="button" variant="ghost" onClick={handleReset} className="text-gray-500">
                Reset to defaults
              </Button>
            </div>
          </form>
        </div>

        {/* Live preview */}
        <div className="lg:col-span-2">
          <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-4">
            <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Sidebar preview</h2>
            <div className="flex justify-center">
              <SidebarPreview
                institutionName={institutionName}
                logoUrl={logoUrl}
                primaryColor={primaryColor}
              />
            </div>
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-xs text-gray-500">
                <span
                  className="w-3 h-3 rounded-full border border-gray-200 flex-shrink-0"
                  style={{ background: primaryColor }}
                />
                Primary: {primaryColor}
              </div>
              <div className="flex items-center gap-2 text-xs text-gray-500">
                <span
                  className="w-3 h-3 rounded-full border border-gray-200 flex-shrink-0"
                  style={{ background: secondaryColor }}
                />
                Accent: {secondaryColor}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
