import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { createTenant } from '@/lib/api/tenants'
import { getAdminErrorMessage } from '@/lib/adminApi'

function validatePassword(pw: string): string | null {
  if (pw.length < 8)            return 'Minimum 8 characters'
  if (!/[A-Z]/.test(pw))        return 'Must contain an uppercase letter'
  if (!/[a-z]/.test(pw))        return 'Must contain a lowercase letter'
  if (!/[0-9]/.test(pw))        return 'Must contain a digit'
  if (!/[^A-Za-z0-9]/.test(pw)) return 'Must contain a special character'
  return null
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

  const passwordError = touched ? validatePassword(adminPassword) : null

  const mut = useMutation({
    mutationFn: () =>
      createTenant({
        name:            name.trim(),
        admin_email:     adminEmail.trim(),
        admin_password:  adminPassword,
        admin_full_name: adminFullName.trim(),
        contact_email:   contactEmail.trim() || undefined,
      }),
    onSuccess: (tenant) => navigate(`/admin/tenants/${tenant.id}`, { replace: true }),
    onError:   (err: unknown) => setError(getAdminErrorMessage(err)),
  })

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setTouched(true)
    if (validatePassword(adminPassword)) return
    setError(null)
    mut.mutate()
  }

  return (
    <main className="max-w-xl mx-auto px-6 py-10">
      <div className="flex items-center gap-3 mb-6">
        <button
          onClick={() => navigate('/admin/tenants')}
          className="p-1 rounded text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors"
          aria-label="Back"
        >
          <ArrowLeft className="h-5 w-5" />
        </button>
        <h2 className="text-xl font-semibold text-gray-900">New Tenant</h2>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <p className="text-sm text-gray-500 mb-6">
          Creates an isolated database schema and seeds an admin user. The admin will receive
          a welcome email after provisioning completes.
        </p>

        <form onSubmit={handleSubmit} className="space-y-5">
          <fieldset className="space-y-1">
            <legend className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
              Institution
            </legend>
            <label className="block text-sm font-medium text-gray-700" htmlFor="name">
              Institution name
            </label>
            <Input
              id="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="MIT University"
              minLength={3}
              maxLength={100}
              required
              autoFocus
            />
            <p className="text-xs text-gray-400 mt-0.5">3–100 characters. Used to derive the URL slug.</p>
          </fieldset>

          <fieldset className="space-y-3">
            <legend className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
              Admin account
            </legend>
            <div className="space-y-1">
              <label className="block text-sm font-medium text-gray-700" htmlFor="admin-full-name">
                Full name
              </label>
              <Input
                id="admin-full-name"
                value={adminFullName}
                onChange={(e) => setAdminFullName(e.target.value)}
                placeholder="Admin User"
                required
              />
            </div>
            <div className="space-y-1">
              <label className="block text-sm font-medium text-gray-700" htmlFor="admin-email">
                Email
              </label>
              <Input
                id="admin-email"
                type="email"
                value={adminEmail}
                onChange={(e) => setAdminEmail(e.target.value)}
                placeholder="admin@university.edu"
                required
              />
            </div>
            <div className="space-y-1">
              <label className="block text-sm font-medium text-gray-700" htmlFor="admin-password">
                Password
              </label>
              <Input
                id="admin-password"
                type="password"
                value={adminPassword}
                onChange={(e) => { setAdminPassword(e.target.value); setTouched(true) }}
                placeholder="Min 8 chars"
                required
              />
              {passwordError && (
                <p className="text-xs text-red-600 mt-0.5">{passwordError}</p>
              )}
              {!passwordError && adminPassword.length > 0 && (
                <p className="text-xs text-green-600 mt-0.5">Password looks good.</p>
              )}
              <p className="text-xs text-gray-400 mt-0.5">
                Requires upper + lowercase + digit + special character.
              </p>
            </div>
          </fieldset>

          <fieldset className="space-y-1">
            <legend className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
              Welcome email (optional)
            </legend>
            <label className="block text-sm font-medium text-gray-700" htmlFor="contact-email">
              Contact email
            </label>
            <Input
              id="contact-email"
              type="email"
              value={contactEmail}
              onChange={(e) => setContactEmail(e.target.value)}
              placeholder="Defaults to admin email if blank"
            />
          </fieldset>

          {error && (
            <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              {error}
            </div>
          )}

          <div className="flex gap-3 pt-1">
            <Button type="submit" disabled={mut.isPending || !!passwordError}>
              {mut.isPending ? 'Provisioning…' : 'Provision tenant'}
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => navigate('/admin/tenants')}
              disabled={mut.isPending}
            >
              Cancel
            </Button>
          </div>
        </form>
      </div>
    </main>
  )
}
