import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { ArrowLeft, CheckCircle2, Copy, Check, Palette, ExternalLink, Lock, Landmark } from 'lucide-react'
import { createTenant } from '@/lib/api/tenants'
import { getAdminErrorMessage } from '@/lib/adminApi'
import type { GovernanceType, Tenant } from '@/lib/api/tenants'

// The two names a university may give the body that approves its curriculum.
// Identical permissions — this only decides the word the tenant's UI will use.
const GOVERNANCE_CHOICES: { value: GovernanceType; label: string; hint: string }[] = [
  {
    value: 'BOARD',
    label: 'Board',
    hint: 'Members appear as “Board Members”. Typical for a Board of Studies.',
  },
  {
    value: 'UNIVERSITY_MEMBERS',
    label: 'University Members',
    hint: 'Members appear as “University Members”. For an academic council model.',
  },
]

function validatePassword(pw: string): string | null {
  if (pw.length < 8)            return 'Minimum 8 characters'
  if (!/[A-Z]/.test(pw))        return 'Must contain an uppercase letter'
  if (!/[a-z]/.test(pw))        return 'Must contain a lowercase letter'
  if (!/[0-9]/.test(pw))        return 'Must contain a digit'
  if (!/[^A-Za-z0-9]/.test(pw)) return 'Must contain a special character'
  return null
}

function DarkInput({
  id, type = 'text', value, onChange, placeholder, required, autoFocus, readOnly, minLength, maxLength,
}: {
  id?: string; type?: string; value: string; onChange?: (e: React.ChangeEvent<HTMLInputElement>) => void
  placeholder?: string; required?: boolean; autoFocus?: boolean; readOnly?: boolean
  minLength?: number; maxLength?: number
}) {
  return (
    <input
      id={id}
      type={type}
      value={value}
      onChange={onChange}
      placeholder={placeholder}
      required={required}
      autoFocus={autoFocus}
      readOnly={readOnly}
      minLength={minLength}
      maxLength={maxLength}
      className="w-full px-3.5 py-2.5 rounded-lg text-sm text-slate-200 placeholder:text-slate-600 outline-none transition-all"
      style={{
        background: readOnly ? 'rgba(255,255,255,0.02)' : 'rgba(255,255,255,0.05)',
        border: '1px solid rgba(255,255,255,0.1)',
        color: readOnly ? '#475569' : undefined,
      }}
      onFocus={(e) => { if (!readOnly) e.currentTarget.style.borderColor = 'rgba(16,185,129,0.4)' }}
      onBlur={(e)  => { if (!readOnly) e.currentTarget.style.borderColor = 'rgba(255,255,255,0.1)' }}
    />
  )
}

function CopyableField({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false)

  function handleCopy() {
    navigator.clipboard.writeText(value).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <div className="space-y-1">
      <p className="text-[10px] font-bold text-slate-500 uppercase tracking-[0.12em]">{label}</p>
      <div className="flex items-center gap-2">
        <code
          className="flex-1 rounded px-3 py-1.5 text-sm font-mono text-slate-200 break-all"
          style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)' }}
        >
          {value}
        </code>
        <button
          onClick={handleCopy}
          className="shrink-0 p-1.5 rounded text-slate-500 transition-colors"
          style={{}}
          onMouseEnter={(e) => { e.currentTarget.style.color = '#e2e8f0'; e.currentTarget.style.background = 'rgba(255,255,255,0.06)' }}
          onMouseLeave={(e) => { e.currentTarget.style.color = ''; e.currentTarget.style.background = '' }}
          title="Copy"
        >
          {copied ? <Check className="h-4 w-4 text-emerald-400" /> : <Copy className="h-4 w-4" />}
        </button>
      </div>
    </div>
  )
}

interface SuccessData {
  tenant: Tenant
  adminEmail: string
  adminPassword: string
}

function ProvisioningSuccess({
  data, onViewDetail, onBackToList,
}: {
  data: SuccessData; onViewDetail: () => void; onBackToList: () => void
}) {
  return (
    <main className="max-w-2xl mx-auto px-8 py-10">
      <div
        className="rounded-xl overflow-hidden"
        style={{ background: 'rgba(12,22,41,0.9)', border: '1px solid rgba(16,185,129,0.2)' }}
      >
        <div
          className="px-6 py-5 flex items-start gap-3"
          style={{ background: 'rgba(16,185,129,0.06)', borderBottom: '1px solid rgba(16,185,129,0.15)' }}
        >
          <CheckCircle2 className="h-6 w-6 text-emerald-400 shrink-0 mt-0.5" />
          <div>
            <h2 className="text-lg font-semibold text-emerald-300">University provisioned</h2>
            <p className="text-sm text-slate-400 mt-0.5">
              <span className="text-slate-200 font-medium">{data.tenant.name}</span> is live. Schema created and admin account seeded.
            </p>
          </div>
        </div>

        <div className="px-6 py-6 space-y-5">
          <CopyableField label="University name"              value={data.tenant.name} />
          <CopyableField label="Institution ID (used at login)" value={data.tenant.slug} />
          <CopyableField label="Admin email"                  value={data.adminEmail} />
          <CopyableField label="Temporary password"           value={data.adminPassword} />

          {(data.tenant.primary_color || data.tenant.logo_url) && (
            <div
              className="rounded-lg px-4 py-3 space-y-1.5"
              style={{ background: 'rgba(16,185,129,0.06)', border: '1px solid rgba(16,185,129,0.15)' }}
            >
              <p className="text-xs font-semibold text-emerald-400">Branding stored</p>
              <div className="flex items-center gap-3 text-xs text-slate-500">
                {data.tenant.primary_color && (
                  <span className="flex items-center gap-1.5">
                    <span
                      className="w-3 h-3 rounded-full border border-white/10 inline-block shadow-sm"
                      style={{ background: data.tenant.primary_color }}
                    />
                    {data.tenant.primary_color}
                  </span>
                )}
                {data.tenant.logo_url && <span className="truncate">{data.tenant.logo_url}</span>}
              </div>
            </div>
          )}

          <div
            className="rounded-lg px-4 py-3 text-sm"
            style={{ background: 'rgba(245,158,11,0.06)', border: '1px solid rgba(245,158,11,0.2)', color: '#fbbf24' }}
          >
            The admin will be prompted to change this password on first login.
          </div>

          <div className="flex gap-3">
            <button
              className="flex-1 py-2.5 rounded-xl text-sm font-semibold text-white transition-all"
              style={{ background: 'linear-gradient(135deg, #10b981, #059669)', boxShadow: '0 0 16px rgba(16,185,129,0.2)' }}
              onClick={onViewDetail}
            >
              View tenant detail
            </button>
            <a
              href="/login"
              target="_blank"
              rel="noopener noreferrer"
              className="flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-xl text-sm font-semibold transition-all"
              style={{
                background: 'rgba(255,255,255,0.04)',
                border: '1px solid rgba(255,255,255,0.1)',
                color: '#cbd5e1',
              }}
            >
              Open login page
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
          </div>
          <button
            onClick={onBackToList}
            className="w-full text-xs text-slate-600 hover:text-slate-400 underline underline-offset-2 transition-colors"
          >
            Back to tenant list
          </button>
        </div>
      </div>
    </main>
  )
}

export default function TenantCreatePage() {
  const navigate = useNavigate()

  const [name,          setName]          = useState('')
  const [adminEmail,    setAdminEmail]    = useState('')
  const [adminPassword, setAdminPassword] = useState('')
  const [adminFullName, setAdminFullName] = useState('')
  const [contactEmail,  setContactEmail]  = useState('')
  const [touched,       setTouched]       = useState(false)
  const [error,         setError]         = useState<string | null>(null)
  const [successData,   setSuccessData]   = useState<SuccessData | null>(null)

  const [logoUrl,        setLogoUrl]        = useState('')
  const [primaryColor,   setPrimaryColor]   = useState('#2563eb')
  const [secondaryColor, setSecondaryColor] = useState('')
  const [governanceType, setGovernanceType] = useState<GovernanceType>('BOARD')

  const passwordError = touched ? validatePassword(adminPassword) : null

  const mut = useMutation({
    mutationFn: () =>
      createTenant({
        name:            name.trim(),
        admin_email:     adminEmail.trim(),
        admin_password:  adminPassword,
        admin_full_name: adminFullName.trim(),
        contact_email:   contactEmail.trim() || undefined,
        logo_url:        logoUrl.trim() || undefined,
        primary_color:   primaryColor.trim() || undefined,
        secondary_color: secondaryColor.trim() || undefined,
        governance_type: governanceType,
      }),
    onSuccess: (tenant) =>
      setSuccessData({ tenant, adminEmail: adminEmail.trim(), adminPassword }),
    onError: (err: unknown) => setError(getAdminErrorMessage(err)),
  })

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setTouched(true)
    if (validatePassword(adminPassword)) return
    setError(null)
    mut.mutate()
  }

  if (successData) {
    return (
      <ProvisioningSuccess
        data={successData}
        onViewDetail={() => navigate(`/admin/tenants/${successData.tenant.id}`, { replace: true })}
        onBackToList={() => navigate('/admin/tenants', { replace: true })}
      />
    )
  }

  const labelCls = 'block text-xs font-semibold text-slate-400'

  return (
    <main className="max-w-5xl mx-auto px-8 py-8">

      {/* Page header */}
      <div className="flex items-center gap-3 mb-8">
        <button
          onClick={() => navigate('/admin/tenants')}
          className="p-1.5 rounded-lg text-slate-600 transition-colors flex-shrink-0"
          onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(255,255,255,0.06)'; e.currentTarget.style.color = '#cbd5e1' }}
          onMouseLeave={(e) => { e.currentTarget.style.background = ''; e.currentTarget.style.color = '' }}
          aria-label="Back"
        >
          <ArrowLeft className="h-5 w-5" />
        </button>
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Provision University</h1>
          <p className="text-sm text-slate-500 mt-0.5">Create an isolated tenant with a seeded admin account</p>
        </div>
      </div>

      {/* Two-column: info panel + form */}
      <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-8">

        {/* Left: provisioning context */}
        <aside className="space-y-4">
          <div
            className="rounded-xl p-5"
            style={{ background: 'rgba(12,22,41,0.8)', border: '1px solid rgba(255,255,255,0.06)' }}
          >
            <h2 className="text-xs font-bold text-slate-400 uppercase tracking-[0.12em] mb-4">
              What gets created
            </h2>
            <ul className="space-y-3">
              {[
                'Isolated PostgreSQL schema',
                'Tenant record with branding',
                'Admin account seeded',
                'First-login password change enforced',
                'Action logged to audit trail',
              ].map((item) => (
                <li key={item} className="flex items-start gap-2.5">
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 flex-shrink-0 mt-0.5" />
                  <span className="text-xs text-slate-400 leading-relaxed">{item}</span>
                </li>
              ))}
            </ul>
          </div>

          <div
            className="rounded-xl p-4"
            style={{ background: 'rgba(16,185,129,0.05)', border: '1px solid rgba(16,185,129,0.15)' }}
          >
            <div className="flex items-start gap-2.5">
              <Lock className="h-3.5 w-3.5 text-emerald-600 flex-shrink-0 mt-0.5" />
              <p className="text-xs text-slate-500 leading-relaxed">
                Each university gets a fully isolated schema. No data is ever shared across tenants.
              </p>
            </div>
          </div>
        </aside>

        {/* Right: form */}
        <div
          className="rounded-xl p-7"
          style={{ background: 'rgba(12,22,41,0.85)', border: '1px solid rgba(255,255,255,0.08)' }}
        >
          <form onSubmit={handleSubmit} className="space-y-7">

            {/* Institution */}
            <section>
              <h3 className="text-[10px] font-bold text-slate-500 uppercase tracking-[0.14em] mb-3">
                Institution
              </h3>
              <div className="space-y-1">
                <label className={labelCls} htmlFor="name">University name</label>
                <DarkInput
                  id="name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="MIT University"
                  minLength={3}
                  maxLength={100}
                  required
                  autoFocus
                />
                <p className="text-[10px] text-slate-600 mt-0.5">3–100 characters. Used to derive the Institution ID (slug).</p>
              </div>
            </section>

            {/* Governance authority — Phase A.
                A display name only: BOARD and UNIVERSITY_MEMBERS have byte-for-byte
                identical permissions. Whichever is chosen is the word this tenant's
                entire UI will use for the body that approves curriculum. */}
            <section>
              <h3 className="text-[10px] font-bold text-slate-500 uppercase tracking-[0.14em] mb-3 flex items-center gap-1.5">
                <Landmark className="h-3 w-3 text-slate-600" />
                Academic governance authority
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {GOVERNANCE_CHOICES.map((choice) => {
                  const selected = governanceType === choice.value
                  return (
                    <button
                      key={choice.value}
                      type="button"
                      onClick={() => setGovernanceType(choice.value)}
                      className="rounded-xl p-4 text-left transition-colors"
                      style={{
                        background: selected ? 'rgba(59,130,246,0.10)' : 'rgba(255,255,255,0.02)',
                        border: selected
                          ? '1px solid rgba(59,130,246,0.55)'
                          : '1px solid rgba(255,255,255,0.08)',
                      }}
                      aria-pressed={selected}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-bold text-slate-100">{choice.label}</span>
                        {selected && <CheckCircle2 className="h-4 w-4 text-blue-400" />}
                      </div>
                      <p className="mt-1 text-[11px] leading-relaxed text-slate-500">
                        {choice.hint}
                      </p>
                    </button>
                  )
                })}
              </div>
              <p className="text-[10px] text-slate-600 mt-2">
                Display name only — permissions are identical either way. This body reviews, approves
                and locks curriculum; Deans prepare and publish it.
              </p>
            </section>

            {/* Admin account */}
            <section>
              <h3 className="text-[10px] font-bold text-slate-500 uppercase tracking-[0.14em] mb-3">
                Admin account
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
                <div className="space-y-1">
                  <label className={labelCls} htmlFor="admin-full-name">Full name</label>
                  <DarkInput
                    id="admin-full-name"
                    value={adminFullName}
                    onChange={(e) => setAdminFullName(e.target.value)}
                    placeholder="Admin User"
                    required
                  />
                </div>
                <div className="space-y-1">
                  <label className={labelCls} htmlFor="admin-email">Email</label>
                  <DarkInput
                    id="admin-email"
                    type="email"
                    value={adminEmail}
                    onChange={(e) => setAdminEmail(e.target.value)}
                    placeholder="admin@university.edu"
                    required
                  />
                </div>
              </div>
              <div className="space-y-1">
                <label className={labelCls} htmlFor="admin-password">Temporary password</label>
                <DarkInput
                  id="admin-password"
                  type="password"
                  value={adminPassword}
                  onChange={(e) => { setAdminPassword(e.target.value); setTouched(true) }}
                  placeholder="Min 8 chars — upper, lower, digit, special"
                  required
                />
                {passwordError && (
                  <p className="text-xs mt-0.5" style={{ color: '#f87171' }}>{passwordError}</p>
                )}
                {!passwordError && adminPassword.length > 0 && (
                  <p className="text-xs mt-0.5 text-emerald-500">Password looks good.</p>
                )}
                <p className="text-[10px] text-slate-600 mt-0.5">
                  Must contain uppercase, lowercase, digit, and special character. Admin must change on first login.
                </p>
              </div>
            </section>

            {/* Optional fields: contact email + branding */}
            <section>
              <h3 className="text-[10px] font-bold text-slate-500 uppercase tracking-[0.14em] mb-3 flex items-center gap-1.5">
                <Palette className="h-3 w-3 text-slate-600" />
                Branding &amp; contact
                <span className="text-slate-700 font-normal normal-case text-[9px] tracking-normal">(optional)</span>
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
                <div className="space-y-1">
                  <label className={labelCls} htmlFor="contact-email">Contact email</label>
                  <DarkInput
                    id="contact-email"
                    type="email"
                    value={contactEmail}
                    onChange={(e) => setContactEmail(e.target.value)}
                    placeholder="Defaults to admin email"
                  />
                </div>
                <div className="space-y-1">
                  <label className={labelCls} htmlFor="logo-url">University logo URL</label>
                  <DarkInput
                    id="logo-url"
                    type="url"
                    value={logoUrl}
                    onChange={(e) => setLogoUrl(e.target.value)}
                    placeholder="https://university.edu/logo.png"
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className={labelCls} htmlFor="primary-color">Primary color</label>
                  <div className="flex items-center gap-2">
                    <input
                      id="primary-color"
                      type="color"
                      value={primaryColor}
                      onChange={(e) => setPrimaryColor(e.target.value)}
                      className="w-9 h-9 rounded-lg cursor-pointer p-0.5 flex-shrink-0"
                      style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)' }}
                    />
                    <DarkInput
                      value={primaryColor}
                      onChange={(e) => setPrimaryColor(e.target.value)}
                      placeholder="#2563eb"
                      maxLength={7}
                    />
                  </div>
                </div>
                <div className="space-y-1">
                  <label className={labelCls} htmlFor="secondary-color">Secondary color</label>
                  <div className="flex items-center gap-2">
                    <input
                      id="secondary-color"
                      type="color"
                      value={secondaryColor || '#06b6d4'}
                      onChange={(e) => setSecondaryColor(e.target.value)}
                      className="w-9 h-9 rounded-lg cursor-pointer p-0.5 flex-shrink-0"
                      style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)' }}
                    />
                    <DarkInput
                      value={secondaryColor}
                      onChange={(e) => setSecondaryColor(e.target.value)}
                      placeholder="#06b6d4"
                      maxLength={7}
                    />
                  </div>
                </div>
              </div>
            </section>

            {error && (
              <div
                className="text-sm rounded-lg px-3 py-2.5"
                style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)', color: '#f87171' }}
              >
                {error}
              </div>
            )}

            <div
              className="flex items-center justify-between gap-4 pt-2"
              style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}
            >
              <div className="flex gap-3">
                <button
                  type="submit"
                  disabled={mut.isPending || !!passwordError}
                  className="px-6 py-2.5 rounded-xl text-sm font-semibold text-white transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                  style={{
                    background: 'linear-gradient(135deg, #10b981, #059669)',
                    boxShadow: '0 0 16px rgba(16,185,129,0.2)',
                  }}
                >
                  {mut.isPending ? 'Provisioning…' : 'Provision university'}
                </button>
                <button
                  type="button"
                  onClick={() => navigate('/admin/tenants')}
                  disabled={mut.isPending}
                  className="px-5 py-2.5 rounded-xl text-sm font-medium text-slate-400 transition-all disabled:opacity-50"
                  style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)' }}
                  onMouseEnter={(e) => { e.currentTarget.style.color = '#cbd5e1' }}
                  onMouseLeave={(e) => { e.currentTarget.style.color = '' }}
                >
                  Cancel
                </button>
              </div>
              <div className="flex items-center gap-1.5 flex-shrink-0">
                <Lock className="h-3 w-3 text-slate-700" />
                <p className="text-[10px] text-slate-700">Isolated schema · Logged</p>
              </div>
            </div>

          </form>
        </div>
      </div>
    </main>
  )
}
