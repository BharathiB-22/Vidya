import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { ArrowLeft, Building2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { createTenant } from '@/lib/api/tenants'
import { getAdminErrorMessage } from '@/lib/adminApi'

export default function TenantCreatePage() {
  const navigate = useNavigate()

  const [name,          setName]          = useState('')
  const [adminEmail,    setAdminEmail]    = useState('')
  const [adminPassword, setAdminPassword] = useState('')
  const [adminFullName, setAdminFullName] = useState('')
  const [contactEmail,  setContactEmail]  = useState('')
  const [error,         setError]         = useState<string | null>(null)

  const mut = useMutation({
    mutationFn: () =>
      createTenant({
        name: name.trim(),
        admin_email: adminEmail.trim(),
        admin_password: adminPassword,
        admin_full_name: adminFullName.trim(),
        contact_email: contactEmail.trim() || undefined,
      }),
    onSuccess: (tenant) => navigate(`/admin/tenants/${tenant.id}`, { replace: true }),
    onError: (err: unknown) => setError(getAdminErrorMessage(err)),
  })

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    mut.mutate()
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center gap-3">
        <button onClick={() => navigate('/admin/tenants')} className="text-gray-500 hover:text-gray-700">
          <ArrowLeft className="h-5 w-5" />
        </button>
        <Building2 className="h-5 w-5 text-indigo-600" />
        <span className="text-lg font-semibold text-indigo-700">New Tenant</span>
      </header>

      <main className="max-w-xl mx-auto px-6 py-10">
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-base font-semibold text-gray-900 mb-1">Provision a new institution</h2>
          <p className="text-sm text-gray-500 mb-6">
            This creates an isolated database schema and seeds an admin user. The admin will receive
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
                  onChange={(e) => setAdminPassword(e.target.value)}
                  placeholder="Min 8 chars, upper + lower + digit + special"
                  required
                />
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
              <Button type="submit" disabled={mut.isPending}>
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
    </div>
  )
}
