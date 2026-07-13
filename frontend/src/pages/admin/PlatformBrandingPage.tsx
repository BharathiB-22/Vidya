import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Palette, RefreshCw, Shield, Globe, Phone, Mail, Image, Check } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { addToast } from '@/hooks/useToast'
import { getAdminErrorMessage } from '@/lib/adminApi'
import { getPlatformBranding, updatePlatformBranding, type PlatformBranding } from '@/lib/api/platform'
import { tint } from '@/lib/platformPalette'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const inputCls = 'w-full px-3 py-2.5 text-sm text-slate-200 rounded-lg outline-none transition-all'
const inputStyle = { background: 'var(--pc-t-overlay-05)', border: '1px solid var(--pc-t-overlay-10)' }
const labelCls = 'block text-xs font-semibold text-slate-400 mb-1.5'

function SectionCard({
  icon: Icon, title, iconColor, children,
}: {
  icon: typeof Globe; title: string; iconColor: string; children: React.ReactNode
}) {
  return (
    <div
      className="rounded-xl p-6"
      style={{
        background: 'linear-gradient(180deg, var(--pc-t-surf2-95) 0%, var(--pc-t-surf4-95) 100%)',
        border: '1px solid var(--pc-t-overlay-08)',
      }}
    >
      <div className="flex items-center gap-3 mb-5">
        <div
          className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0"
          style={{ background: tint(iconColor, 9.41), border: `1px solid ${tint(iconColor, 18.82)}` }}
        >
          <Icon className="h-[18px] w-[18px]" style={{ color: iconColor }} />
        </div>
        <h2 className="text-base font-bold text-white">{title}</h2>
      </div>
      {children}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Color picker field
// ---------------------------------------------------------------------------

function ColorField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div>
      <label className={labelCls}>{label}</label>
      <div className="flex items-center gap-2">
        <input
          type="color"
          value={value || '#10b981'}
          onChange={(e) => onChange(e.target.value)}
          className="h-9 w-9 rounded-lg cursor-pointer border-0 flex-shrink-0"
          style={{ background: 'transparent', padding: 1 }}
        />
        <input
          className={`${inputCls} flex-1`}
          style={inputStyle}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="#10b981"
          maxLength={7}
        />
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Branding preview
// ---------------------------------------------------------------------------

function BrandingPreview({ form }: { form: Partial<PlatformBranding> }) {
  return (
    /* pc-brand-preview: the labels in here sit on the *tenant's* brand colour,
       not on console chrome, so they stay white whatever theme the console is
       wearing. See platform-theme.css. */
    <div
      className="pc-brand-preview rounded-xl overflow-hidden"
      style={{ border: '1px solid var(--pc-t-overlay-08)' }}
    >
      {/* Mock login bar */}
      <div
        className="flex items-center gap-3 px-4 py-3"
        style={{ background: form.primary_color ?? '#10b981', minHeight: 48 }}
      >
        {form.logo_url ? (
          <img src={form.logo_url} alt="logo" className="h-7 w-7 rounded object-contain" />
        ) : (
          <div
            className="h-7 w-7 rounded flex items-center justify-center text-xs font-bold text-white"
            style={{ background: 'rgba(0,0,0,0.25)' }}
          >
            {(form.platform_name ?? 'V').slice(0, 1)}
          </div>
        )}
        <span className="text-sm font-bold text-white">{form.platform_name ?? 'VIDYA AI'}</span>
        <span className="ml-auto text-xs text-white/60">{form.company_name ?? 'SherpaVector'}</span>
      </div>

      {/* Mock content */}
      <div
        className="px-4 py-4 space-y-2"
        style={{ background: 'var(--pc-t-surf5-95)' }}
      >
        <div className="h-2 rounded-full w-3/4" style={{ background: 'var(--pc-t-overlay-07)' }} />
        <div className="h-2 rounded-full w-1/2" style={{ background: 'var(--pc-t-overlay-04)' }} />
        <div className="h-2 rounded-full w-2/3" style={{ background: 'var(--pc-t-overlay-04)' }} />
        <div className="mt-3 flex gap-2">
          <div
            className="h-6 w-20 rounded text-[9px] flex items-center justify-center text-white font-bold"
            style={{ background: form.primary_color ?? '#10b981' }}
          >
            Primary
          </div>
          <div
            className="h-6 w-20 rounded text-[9px] flex items-center justify-center text-white font-bold"
            style={{ background: form.accent_color ?? '#6366f1' }}
          >
            Accent
          </div>
        </div>
        {form.support_email && (
          <p className="text-[10px] text-slate-600 mt-2">Support: {form.support_email}</p>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main branding form
// ---------------------------------------------------------------------------

type BrandingForm = {
  platform_name: string
  company_name: string
  support_email: string
  support_phone: string
  logo_url: string
  favicon_url: string
  primary_color: string
  accent_color: string
}

function fromBranding(b: PlatformBranding): BrandingForm {
  return {
    platform_name: b.platform_name,
    company_name: b.company_name,
    support_email: b.support_email ?? '',
    support_phone: b.support_phone ?? '',
    logo_url: b.logo_url ?? '',
    favicon_url: b.favicon_url ?? '',
    primary_color: b.primary_color ?? '#10b981',
    accent_color: b.accent_color ?? '#6366f1',
  }
}

function toDelta(form: BrandingForm, original: PlatformBranding): Partial<Omit<PlatformBranding, 'id' | 'updated_at'>> {
  const delta: Record<string, string | null | undefined> = {}
  const map: [keyof BrandingForm, keyof PlatformBranding][] = [
    ['platform_name', 'platform_name'],
    ['company_name', 'company_name'],
    ['support_email', 'support_email'],
    ['support_phone', 'support_phone'],
    ['logo_url', 'logo_url'],
    ['favicon_url', 'favicon_url'],
    ['primary_color', 'primary_color'],
    ['accent_color', 'accent_color'],
  ]
  for (const [fk, bk] of map) {
    const formVal = form[fk] || null
    const origVal = (original[bk] as string | null) ?? null
    if (formVal !== origVal) delta[bk] = formVal ?? undefined
  }
  return delta
}

export default function PlatformBrandingPage() {
  const qc = useQueryClient()
  const { data: branding, isLoading, isError, refetch } = useQuery({
    queryKey: ['platform-branding'],
    queryFn: getPlatformBranding,
  })

  const [form, setForm] = useState<BrandingForm | null>(null)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (branding && !form) setForm(fromBranding(branding))
  }, [branding]) // eslint-disable-line react-hooks/exhaustive-deps

  const mut = useMutation({
    mutationFn: () => {
      if (!form || !branding) throw new Error('Not ready')
      const delta = toDelta(form, branding)
      if (Object.keys(delta).length === 0) return Promise.resolve(branding)
      return updatePlatformBranding(delta)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['platform-branding'] })
      addToast('Branding saved successfully.', 'success')
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    },
    onError: (err) => addToast(getAdminErrorMessage(err), 'error'),
  })

  function field(key: keyof BrandingForm) {
    return {
      value: form?.[key] ?? '',
      onChange: (e: React.ChangeEvent<HTMLInputElement>) =>
        setForm((f) => f ? { ...f, [key]: e.target.value } : f),
    }
  }

  return (
    <main className="max-w-screen-xl mx-auto px-8 py-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-white">Platform Branding</h1>
          <p className="text-sm text-slate-400 mt-0.5">
            Configure the platform identity displayed on login pages and throughout the console
          </p>
        </div>
        <div className="flex items-center gap-3">
          {branding && (
            <p className="text-xs text-slate-600">
              Last updated {new Date(branding.updated_at).toLocaleString()}
            </p>
          )}
          <button
            onClick={() => refetch()}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-semibold text-slate-300 transition-all"
            style={{ background: 'var(--pc-t-overlay-05)', border: '1px solid var(--pc-t-overlay-10)' }}
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </button>
        </div>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-24 text-slate-600">
          <RefreshCw className="h-5 w-5 animate-spin mr-2" />
          Loading branding configuration…
        </div>
      )}

      {isError && (
        <div
          className="rounded-xl px-6 py-5 mb-6 flex items-center gap-3"
          style={{ background: 'var(--pc-t-red-08)', border: '1px solid var(--pc-t-red-20)' }}
        >
          <Shield className="h-5 w-5 text-red-400 flex-shrink-0" />
          <p className="text-sm font-semibold text-red-300">Failed to load branding configuration</p>
          <button onClick={() => refetch()} className="ml-auto text-xs text-slate-400 hover:text-slate-200">Retry</button>
        </div>
      )}

      {form && (
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">

          {/* Left column — edit fields */}
          <div className="xl:col-span-2 space-y-6">

            {/* Identity */}
            <SectionCard icon={Globe} title="Platform Identity" iconColor="var(--pc-indigo-500)">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className={labelCls}>Platform Name</label>
                  <input className={inputCls} style={inputStyle} {...field('platform_name')} maxLength={100} />
                </div>
                <div>
                  <label className={labelCls}>Company Name</label>
                  <input className={inputCls} style={inputStyle} {...field('company_name')} maxLength={100} />
                </div>
              </div>
            </SectionCard>

            {/* Contact */}
            <SectionCard icon={Mail} title="Support Contact" iconColor="var(--pc-blue-400)">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className={labelCls}>Support Email</label>
                  <div className="flex items-center gap-2">
                    <Mail className="h-4 w-4 text-slate-600 flex-shrink-0" />
                    <input type="email" className={`${inputCls} flex-1`} style={inputStyle} {...field('support_email')} placeholder="support@example.com" />
                  </div>
                </div>
                <div>
                  <label className={labelCls}>Support Phone</label>
                  <div className="flex items-center gap-2">
                    <Phone className="h-4 w-4 text-slate-600 flex-shrink-0" />
                    <input className={`${inputCls} flex-1`} style={inputStyle} {...field('support_phone')} placeholder="+91 80 1234 5678" />
                  </div>
                </div>
              </div>
            </SectionCard>

            {/* Assets */}
            <SectionCard icon={Image} title="Logo & Favicon" iconColor="var(--pc-amber-500)">
              <div className="space-y-4">
                <div>
                  <label className={labelCls}>Logo URL</label>
                  <div className="flex items-center gap-3">
                    {form.logo_url ? (
                      <img src={form.logo_url} alt="logo" className="h-9 w-9 rounded-lg object-contain flex-shrink-0"
                        style={{ background: 'var(--pc-t-overlay-05)', border: '1px solid var(--pc-t-overlay-10)' }} />
                    ) : (
                      <div className="h-9 w-9 rounded-lg flex items-center justify-center flex-shrink-0"
                        style={{ background: 'var(--pc-t-overlay-05)', border: '1px solid var(--pc-t-overlay-10)' }}>
                        <Image className="h-4 w-4 text-slate-600" />
                      </div>
                    )}
                    <input className={`${inputCls} flex-1`} style={inputStyle} {...field('logo_url')} placeholder="https://your-domain.com/logo.png" />
                  </div>
                </div>
                <div>
                  <label className={labelCls}>Favicon URL</label>
                  <input className={inputCls} style={inputStyle} {...field('favicon_url')} placeholder="https://your-domain.com/favicon.ico" />
                </div>
              </div>
            </SectionCard>

            {/* Colors */}
            <SectionCard icon={Palette} title="Brand Colors" iconColor="var(--pc-violet-400)">
              <div className="grid grid-cols-2 gap-4">
                <ColorField
                  label="Primary Color"
                  value={form.primary_color}
                  onChange={(v) => setForm((f) => f ? { ...f, primary_color: v } : f)}
                />
                <ColorField
                  label="Accent Color"
                  value={form.accent_color}
                  onChange={(v) => setForm((f) => f ? { ...f, accent_color: v } : f)}
                />
              </div>
              <div
                className="mt-4 rounded-lg px-3 py-2 text-[11px] text-slate-500"
                style={{ background: 'var(--pc-t-overlay-2p5)', border: '1px solid var(--pc-t-overlay-05)' }}
              >
                Colors affect the platform header, buttons, and accent elements across the Super Admin console and tenant portals.
              </div>
            </SectionCard>

            {/* Save */}
            <Button
              onClick={() => mut.mutate()}
              disabled={mut.isPending}
              className="w-full py-3 text-base font-bold"
              style={{
                /* Green means "saved", not "primary". The default state stays
                   indigo — which --pc-indigo already renders as a readable blue
                   in the light and dark themes. */
                background: saved
                  ? 'linear-gradient(135deg, var(--pc-emerald-500), var(--pc-emerald-600))'
                  : 'linear-gradient(135deg, var(--pc-indigo-500), var(--pc-indigo-600))',
                color: 'var(--pc-accent-fg)',
              }}
            >
              {mut.isPending ? (
                <span className="flex items-center gap-2">
                  <RefreshCw className="h-4 w-4 animate-spin" /> Saving…
                </span>
              ) : saved ? (
                <span className="flex items-center gap-2">
                  <Check className="h-4 w-4" /> Saved!
                </span>
              ) : (
                'Save Branding'
              )}
            </Button>
          </div>

          {/* Right column — preview */}
          <div className="space-y-4">
            <div
              className="rounded-xl p-4"
              style={{
                background: 'linear-gradient(180deg, var(--pc-t-surf2-95) 0%, var(--pc-t-surf4-95) 100%)',
                border: '1px solid var(--pc-t-overlay-08)',
              }}
            >
              <p className="text-xs font-bold text-slate-500 uppercase tracking-wide mb-4">Live Preview</p>
              <BrandingPreview form={form} />
            </div>
            <div
              className="rounded-xl px-4 py-3 text-[11px] text-slate-500 space-y-1"
              style={{ background: 'var(--pc-t-overlay-2p5)', border: '1px solid var(--pc-t-overlay-05)' }}
            >
              <p className="font-semibold text-slate-400">Where branding is applied</p>
              <ul className="space-y-0.5 pl-2">
                <li>• Super Admin login page</li>
                <li>• Platform console header</li>
                <li>• Tenant portal login pages</li>
                <li>• Email templates (if configured)</li>
              </ul>
            </div>
          </div>
        </div>
      )}
    </main>
  )
}
